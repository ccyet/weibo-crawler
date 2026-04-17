# weibo-crawler

用于抓取指定微博 UID 的发帖与专栏文章，输出为 `CSV` 和 `JSONL`。

## 功能

- 抓取指定 UID 的微博发帖
- 抓取专栏/长文内容
- 支持翻页
- 支持登录 Cookie
- 自动展开长文
- 输出结构化数据到本地目录

## 安装

```bash
pip install -r requirements.txt
```

## 使用

最基础用法：

```bash
python weibo_crawler.py --uid 2016713117 --out ./weibo_out
```

带登录态运行：

```bash
python weibo_crawler.py \
  --uid 2016713117 \
  --cookie "SUB=...; SUBP=...; XSRF-TOKEN=..." \
  --max-post-pages 20 \
  --max-article-pages 10 \
  --out ./weibo_out
```

## 参数

- `--uid`：微博用户 UID，必填
- `--cookie`：登录 Cookie，可选，建议带上
- `--max-post-pages`：最多抓取多少页微博发帖，默认 `10`
- `--max-article-pages`：最多抓取多少页专栏，默认 `10`
- `--out`：输出目录，默认 `./output`
- `--sleep`：请求间隔秒数，默认 `1.0`
- `--timeout`：请求超时秒数，默认 `20`

## 输出文件

运行后会在输出目录生成：

- `posts.jsonl`
- `posts.csv`
- `articles.jsonl`
- `articles.csv`
- `manifest.json`

## 说明

1. 微博接口有反爬，强烈建议使用自己的 Cookie。
2. 未登录或风控时，可能返回空数据、重复第一页或被限制访问。
3. 若长文正文为空，通常是登录态失效、接口变更或该条微博无长文。
4. 本脚本偏向自用与研究，不保证长期兼容微博接口变动。

## 输出字段示例

发帖数据常见字段：

- `id`
- `mblogid`
- `created_at`
- `text_raw`
- `source`
- `reposts_count`
- `comments_count`
- `attitudes_count`
- `pic_num`
- `pics`
- `page_info`
- `isLongText`
- `longTextContent`

专栏数据会额外尽量保留文章相关字段。

## 免责声明

请仅在合法、合规、符合目标平台规则的前提下使用。使用者需自行承担实际运行和数据使用责任。
