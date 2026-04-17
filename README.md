# weibo-crawler

用于抓取指定微博 UID 的 V+ 发帖和专栏文章，默认通过 `config.json` 配置，适合 Windows 下直接双击运行。

## 安装

```bash
pip install -r requirements.txt
```

## 使用方式

### 方式 1：双击运行

1. 打开 `config.json`
2. 填好 `uid` 和你自己的登录 `cookie`
3. 双击 `run.bat`

脚本会在 `output/<uid>/<timestamp>/` 下生成结果。

### 方式 2：命令行运行

默认读取当前目录的 `config.json`：

```bash
python weibo_crawler.py
```

也支持显式指定配置文件或临时覆盖参数：

```bash
python weibo_crawler.py --config ./config.json
python weibo_crawler.py --uid 2016713117 --cookie "SUB=...; SUBP=..."
```

## 配置项

`config.json` / `config.example.json` 字段：

- `uid`: 微博 UID
- `cookie`: 已登录 Cookie
- `out_dir`: 输出根目录
- `sleep_sec`: 请求间隔秒数
- `timeout_sec`: 请求超时秒数
- `max_post_pages`: 最多抓多少页微博
- `max_article_pages`: 最多抓多少页文章候选
- `save_raw`: 是否在结果中保留原始响应
- `fail_on_unknown_article`: 遇到无法解析的文章候选时是否直接失败

## 输出文件

每次运行都会创建独立目录，并输出：

- `posts.jsonl`
- `posts.csv`
- `articles.jsonl`
- `articles.csv`
- `skipped_unknown.jsonl`
- `errors.jsonl`
- `manifest.json`

## 行为说明

- 启动前会先做鉴权预检，Cookie 失效不会再伪装成成功
- V+ 发帖只保留“明确识别为会员/付费可见”的微博
- 专栏文章会继续访问 `ttarticle/p/show?id=...` 解析正文
- 如果某条内容无法明确识别或解析，会写入 `skipped_unknown.jsonl` 或 `errors.jsonl`

## 测试

```bash
python -m unittest discover -s tests -v
```
