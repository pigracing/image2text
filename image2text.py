# encoding:utf-8
import io
import json
import base64
import re
import os
import html
from urllib.parse import urlparse

import requests

import plugins
from bridge.context import ContextType
from bridge.reply import Reply, ReplyType
from common.log import logger
from plugins import *
from channel.chat_message import ChatMessage
from channel.wx849.wx849_message import WX849Message
from common.tmp_dir import TmpDir
from common.expired_dict import ExpiredDict

@plugins.register(
    name="Image2Text",
    desire_priority=9,
    hidden=False,
    desc="支持图生文",
    version="0.0.1",
    author="pigracing",
)
class Image2Text(Plugin):

    def __init__(self):
        super().__init__()
        try:
            self.config = super().load_config()
            if not self.config:
                self.config = self._load_config_template()
            self.invoking_reply = self.config.get("#invoking_reply#","🪄✨ 正在为您召唤魔法，稍等一会儿，马上就好。")
            self.error_reply = self.config.get("#error_reply#","😮💨看起来像是服务器在做深呼吸，稍等一下，它会回来的。")
            logger.info(f"[Image2Text] inited, config={self.config}")
            self.images_cache = ExpiredDict(60 * 5)
            self.handlers[Event.ON_HANDLE_CONTEXT] = self.on_handle_context
        except Exception as e:
            logger.error(f"[Image2Text] 初始化异常：{e}")
            raise "[Image2Text] init failed, ignore "

    def on_handle_context(self, e_context: EventContext, retry_count: int = 0):
        try:
            context = e_context["context"]
            print(context.type)
            if context.type not in [
                ContextType.TEXT,
                ContextType.IMAGE,
                'XML'
            ]:
                return
            self.open_ai_api_base = self.config.get("open_ai_api_base", "")
            self.open_ai_api_key = self.config.get("open_ai_api_key", "")
            self.open_ai_model = self.config.get("open_ai_model","")
            self.prompt = self.config.get("prompt", "")
            content = context["content"]
            user_text = None
            if context.type == ContextType.IMAGE:
               wx849_msg:WX849Message = context["msg"]
               cdnthumbaeskey = wx849_msg.image_info.get("aeskey")
               if cdnthumbaeskey is None:
                  print("Warning: 'cdnthumbaeskey' is missing")
                  return
               self.images_cache[str(cdnthumbaeskey)] = content
               reply = Reply(ReplyType.TEXT, "如果您想让我分析图片，请在发完图片5分钟内，引用图片，发送以分析开头的指令，例如分析一下图片中都有什么")
               e_context["reply"] = reply
               e_context.action = EventAction.BREAK_PASS
               return
            else:
               print('image2text--处理文本')
               wx849_msg:WX849Message = context["msg"]
               msg_type = wx849_msg.msg_type
               #当引用图片时，才有效
               if msg_type == 49:
                  cdnthumbaeskey = ''
                  if wx849_msg.quoted_message is None:
                     logger.debug("没有找到引用的内容信息，请注意图片的时效性")
                     return 
                  quoted_message_str = wx849_msg.quoted_message.get("Content")
                  match = re.search(r'cdnthumbaeskey="([^"]+)"', quoted_message_str)
                  if match: 
                     cdnthumbaeskey = match.group(1)
                  else:
                     logger.debug("没有找到cdnthumbaeskey！")
                     return 

                  if content.startswith(("#invoking_reply#", "#error_reply#", "#translator#")):
                     logger.debug("命中插件保留字，不进行响应")
                     return
                  logger.debug("[image2text] on_handle_context. content: %s" % content)
                  keywords = list(self.config.keys())
                  matching_keywords = [keyword for keyword in keywords if content.startswith(keyword)]
                  if matching_keywords:
                     print(f"匹配到以关键字开头：{matching_keywords[0]}")
                     print(f"匹配到以关键字配置内容：{self.config[matching_keywords[0]]}")
                     if retry_count == 0:
                        reply = Reply(ReplyType.TEXT, self.invoking_reply)
                        channel = e_context["channel"]
                        channel.send(reply, context)
                     self.api_type = self.config[matching_keywords[0]].get("api_type", "")
                     self.open_ai_api_base = self.config[matching_keywords[0]].get("open_ai_api_base", "")
                     self.open_ai_api_key = self.config[matching_keywords[0]].get("open_ai_api_key", "")
                     self.open_ai_model = self.config[matching_keywords[0]].get("open_ai_model","")
                     self.prompt = self.config[matching_keywords[0]].get("prompt", "")
                     self.response_type = self.config[matching_keywords[0]].get("response_type","text")
                     self.response_regex = self.config[matching_keywords[0]].get("response_regex","")
                     openai_chat_url = self.open_ai_api_base
                     openai_headers = self._get_openai_headers()

                     img_url = self.images_cache.get(cdnthumbaeskey)
                     if img_url:
                        with open(img_url, 'rb') as f:
                           img_base64 = base64.b64encode(f.read()).decode('utf-8')
                        img_data = f"data:image/png;base64,{img_base64}"
                        user_text = [
                        {
                         "type": "text",
                         "text": self.prompt+" "+content
                        },
                        {
                         "type": "image_url",
                         "image_url": {
                            "url":img_data
                         }
                        }
                        ]
                        openai_payload = self._get_openai_payload(user_text)
                        #logger.debug(f"[Image2Text-ParseImage] openai_chat_url: {openai_chat_url}, openai_headers: {openai_headers}, openai_payload: {openai_payload}")
                        response = requests.post(openai_chat_url, headers=openai_headers, json=openai_payload, timeout=90)
                        response.raise_for_status()
                        if self.response_type == "text":
                           result = response.json()['choices'][0]['message']['content']
                        else:
                           re_content = response.json()['choices'][0]['message']['content']
                           if self.response_regex:
                              images = re.findall(self.response_regex, re_content)
                              if images:
                                 for image_url in images:
                                   if image_url.startswith("http"):
                                      reply = Reply(ReplyType.IMAGE_URL,image_url)
                                   elif image_url.startswith("data:image"):
                                      print("data:image")
                                      _header, _encoded = image_url.split(",", 1)
                                      base64Content = base64.b64decode(_encoded)
                                      b_img = io.BytesIO(base64Content)
                                      reply = Reply(ReplyType.IMAGE,b_img)
                                   else:
                                      base64Content = base64.b64decode(image_url)
                                      b_img = io.BytesIO(base64Content)
                                      reply = Reply(ReplyType.IMAGE,b_img)
                                   channel = e_context["channel"]
                                   channel.send(reply, context)
                                 e_context.action = EventAction.BREAK_PASS
                                 return
                        reply = Reply(ReplyType.TEXT, result)
                        e_context["reply"] = reply
                        e_context.action = EventAction.BREAK_PASS
                     else:
                        reply = Reply(ReplyType.ERROR, "引用的图片已超过5分钟，请重新发送图片，然后@我进行分析")
                        e_context["reply"] = reply
                        e_context.action = EventAction.BREAK_PASS
                        return
               else:
                   e_context.action = EventAction.CONTINUE
                   return

        except Exception as e:
            if retry_count < 3:
                logger.warning(f"[Image2Text] {str(e)}, retry {retry_count + 1}")
                self.on_handle_context(e_context, retry_count + 1)
                return

            logger.exception(f"[Image2Text] {str(e)}")
            reply = Reply(ReplyType.ERROR, self.error_reply)
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS

    def get_help_text(self, verbose, **kwargs):
        return f'根据设定的关键字调用相应的API服务'

    def _load_config_template(self):
        logger.debug("No Image2Text plugin config.json, use plugins/image2text/config.json.template")
        try:
            plugin_config_path = os.path.join(self.path, "config.json.template")
            if os.path.exists(plugin_config_path):
                with open(plugin_config_path, "r", encoding="utf-8") as f:
                    plugin_conf = json.load(f)
                    return plugin_conf
        except Exception as e:
            logger.exception(e)


    def _get_openai_headers(self):
        return {
            'Authorization': f"Bearer {self.open_ai_api_key}",
            'Host': urlparse(self.open_ai_api_base).netloc
        }

    def _get_openai_payload(self, content):
        messages = [{"role": "user", "content": content}]
        payload = {
            'model': self.open_ai_model,
            'messages': messages
        }
        return payload
