# AstrBot JMComic Plugin

基于 [JMComic-Crawler-Python](https://github.com/hect0x7/JMComic-Crawler-Python) 的 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 插件。

搜索、下载禁漫天堂本子，自动生成 PDF，通过合并转发消息发送到 QQ 群。

## 命令

| 命令 | 说明 | 返回类型 |
|------|------|----------|
| `/jm <ID/名称>` | 下载本子 | 合并转发 PDF |
| `/jm author:<名称>` | 搜索作者并下载 | 合并转发 PDF |
| `/jm 周榜` / `/jm 日榜` / `/jm 月榜` | 排行榜 Top 15 | 文字 |
| `/jmv <ID/关键词>` | 查看本子详情 | 文字 |
| `/jmr [标签]` | 随机本子 | 合并转发 PDF |
| `/jmr 周榜/日榜/月榜` | 从排行榜随机 | 合并转发 PDF |
| `/jmr author:<名称>` | 从该作者随机 | 合并转发 PDF |
| `/jml` | 分类/排序帮助 | 文字 |
| `/jm cancel` | 取消下载 | — |
| `/jm log` | 更新日志 | 文字 |

### 用法示例

```
/jm 422866                  # 按 ID 下载
/jm 璃莹                   # 搜索并下载
/jm author:吉田悟郎         # 搜索作者
/jmr                         # 随机一本
/jmr doujin                  # 从同人标签随机
/jmr 周榜                    # 从周榜随机
/jmr author:ratatatat74     # 从该作者随机
/jmv 422866                  # 查看详情
/jmv author:吉田悟郎         # 搜索作者并展示
```

## 安装

```bash
# 复制到 AstrBot 插件目录
cp -r astrbot_plugin_jmcomic /AstrBot/data/plugins/

# 安装依赖
pip install jmcomic

# 重启 AstrBot
docker restart astrbot
```

NapCat 需要启用本地文件上传（用于合并转发中的 PDF）：

```json
// napcat/config/onebot11_{botQQ}.json
{
  "enableLocalFile2Url": true
}
```

## 配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `download_dir` | `/AstrBot/data/jmcomic/` | 下载目录 |
| `max_concurrent` | `1` | 同时下载数 |
| `auto_clean` | `true` | 完成后自动清理 |
| `bot_uin` | `1000000` | 合并转发显示 QQ |
| `bot_name` | `"JMComic"` | 合并转发显示名称 |
| `batch_size` | `30` | 每批图片数（图片模式） |
| `allow_groups` | `[]` | 群白名单 |
| `allow_users` | `[]` | 用户白名单 |

## 依赖

- [jmcomic](https://github.com/hect0x7/JMComic-Crawler-Python) >= 2.6.0
- AstrBot >= v4.25

## 工作流程

1. 搜索/解析本子 ID
2. 逐章下载图片
3. jmcomic 内置 Feature 导出 PDF
4. 通过 OneBot 原始 API 发送文件到私聊
5. 用文件消息 ID 构造合并转发节点
6. 群聊展示合并转发卡片

## License

MIT
