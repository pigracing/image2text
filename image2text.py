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
from channel.gewechat.gewechat_message import GeWeChatMessage
from common.tmp_dir import TmpDir

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
                ContextType.IMAGE
            ]:
                return
            chat_message:ChatMessage = context["msg"]
            gewe_msg:GeWeChatMessage = chat_message.msg
            msg_type = gewe_msg["Data"]["MsgType"]
            img_buff = gewe_msg["Data"]["ImgBuf"]["buffer"]
            self.open_ai_api_base = self.config.get("open_ai_api_base", "")
            self.open_ai_api_key = self.config.get("open_ai_api_key", "")
            self.open_ai_model = self.config.get("open_ai_model","")
            self.prompt = self.config.get("prompt", "")
            content = context["content"]
            prompt = None
            openai_chat_url = self.open_ai_api_base
            openai_headers = self._get_openai_headers()
            openai_payload = None
            if context.type == ContextType.IMAGE:
               if retry_count == 0:
                   reply = Reply(ReplyType.TEXT, self.invoking_reply)
                   channel = e_context["channel"]
                   channel.send(reply, context)
               img_data = f"data:image/png;base64,{img_buff}"
               user_text = [
                   {
                      "type": "text",
                      "text": self.prompt
                   },
                   {
                      "type": "image_url",
                      "image_url": {
                          "url":img_data
                       }
                   }
               ]
               openai_payload = self._get_openai_payload(user_text)
            else:
               print('先不处理文本')
               return

            logger.debug(f"[Image2Text] openai_chat_url: {openai_chat_url}, openai_headers: {openai_headers}, openai_payload: {openai_payload}")
            response = requests.post(openai_chat_url, headers=openai_headers, json=openai_payload, timeout=60)
            response.raise_for_status()
            result = response.json()['choices'][0]['message']['content']
            reply = Reply(ReplyType.TEXT, result)
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS

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
        logger.debug("No KeywordCall plugin config.json, use plugins/keyword_call/config.json.template")
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
