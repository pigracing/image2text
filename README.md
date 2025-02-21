# image2text
可用于dify-on-wechat和chatgpt-on-wechat的插件，用于图生文，支持兼容openai的API接口。


0.0.1已发布



效果如下图
<div align="center">
<img width="700" src="./docs/1WechatIMG60579.png">
</div>

<div align="center">
<img width="700" src="./docs/1WechatIMG60586.png">
</div>




安装后，记得cp config.json.template config.json

config.json 配置说明

```bash
{
  "#invoking_reply#": "🪄✨ 正在为您召唤魔法，稍等一会儿，马上就好。",
  "#error_reply#": "😮💨看起来像是服务器在做深呼吸，稍等一下，它会回来的。",
  "open_ai_api_base": "https://api-url/v1/chat/completions",
  "open_ai_api_key": "",
  "open_ai_model": "",
  "prompt":  "分析图片中都有些什么"
}

```

