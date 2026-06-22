# AstrBot JMComic Plugin

基于 [JMComic-Crawler-Python](https://github.com/hect0x7/JMComic-Crawler-Python) 的 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 插件。

搜索、下载禁漫天堂本子，自动生成 PDF，通过合并转发消息发送到 QQ 群。

> **免责声明**
>
> 本项目为 **实验性个人项目**，由 AI (Claude Code) 辅助生成，仅供学习和研究目的。
>
> - 使用者应遵守当地法律法规，自行承担使用本插件的全部责任
> - 请勿滥用本插件进行批量爬取或对目标服务造成压力
> - 本插件不对第三方 API 的可用性、数据完整性作任何保证
> - 如因使用本插件产生任何法律问题，项目贡献者不承担任何责任
> - 本项目与 JMComic 禁漫天堂无任何关联或合作关系

---

## 命令总览

| 命令 | 说明 | 返回类型 |
|------|------|----------|
| `/jm <ID/名称>` | 按 ID 或名称下载本子 | 合并转发 PDF |
| `/jm author:<名称>` | 按作者名搜索并下载 | 合并转发 PDF |
| `/jm 周榜` / `日榜` / `月榜` | 查看排行榜 Top 15 | 文字 |
| `/jmv <ID/关键词>` | 查看本子详情 | 文字 |
| `/jmr [标签]` | 随机抽取一本本子 | 合并转发 PDF |
| `/jmr 周榜/日榜/月榜` | 从排行榜随机抽取 | 合并转发 PDF |
| `/jmr author:<名称>` | 从该作者随机抽取 | 合并转发 PDF |
| `/jml` | 查看分类/排序/时间说明 | 文字 |
| `/jm cancel` | 取消正在进行的下载 | — |
| `/jm log` | 查看更新日志 | 文字 |

---

## 详细用法

### `/jm <ID/名称>` — 下载本子

支持三种输入方式：

1. **禁漫车号** — 直接输入数字 ID

    ```
    /jm 422866
    ```

2. **本子名称** — 输入关键词搜索，自动选择第一个结果

    ```
    /jm 璃莹
    /jm 董卓 上+下
    ```

3. **作者搜索** — 加 `author:` 前缀

    ```
    /jm author:吉田悟郎
    /jm author:ratatatat74
    ```

**执行流程：**
- 本子超过 100 页时会要求二次确认，再次发送相同命令即可确认下载
- 下载过程中可随时 `/jm cancel` 取消
- 文件发给你的私聊 → 群聊只显示合并转发卡片，原始文件自动撤回

---

### `/jm 周榜` / `/jm 日榜` / `/jm 月榜` — 查看排行榜

```
/jm 周榜
/jm 日榜
/jm 月榜
```

返回 Top 15 列表（排名 + 本子标题 + ID），**不会触发下载**。

---

### `/jmv <ID/关键词>` — 查看本子详情

不下载，只展示信息。支持：

1. **按 ID 查看** — 显示完整信息（标题、作者、页数、点赞、标签、人物、作品、章节列表）

    ```
    /jmv 422866
    ```

2. **按关键词搜索** — 搜索并展示第一个结果

    ```
    /jmv 吉田悟郎
    /jmv 董卓
    ```

---

### `/jmr` — 随机本子

四种随机方式：

1. **完全随机**

    ```
    /jmr
    ```

2. **按标签随机** — 指定分类（doujin、hanman、single 等）

    ```
    /jmr doujin
    /jmr 全彩
    ```

3. **从排行榜随机** — 从周/日/月榜中随机抽取

    ```
    /jmr 周榜
    /jmr 日榜
    /jmr 月榜
    ```

4. **从作者随机** — 指定作者名，随机抽取该作者的一本

    ```
    /jmr author:吉田悟郎
    /jmr author:ratatatat74
    ```

---

### `/jml` — 分类参考

```
/jml
```

显示可用的分类标签（doujin、hanman、single 等）、排序方式（mr、mv、tf、md）和时间范围（a、t、w、m）。

---

### `/jm cancel` — 取消下载

如果在下载过程中想中断：

```
/jm cancel
```

取消后当前章节下载完即停止，不会继续下载后续章节。

---

## 安装

```bash
# 复制到 AstrBot 插件目录
cp -r astrbot_plugin_jmcomic /AstrBot/data/plugins/

# 安装依赖
pip install jmcomic

# 重启 AstrBot
docker restart astrbot
```

### NapCat 配置

合并转发中的 PDF 文件上传依赖 NapCat 的本地文件转 URL 功能：

```json
// napcat/config/onebot11_{你的BotQQ}.json
{
  "enableLocalFile2Url": true
}
```

配置后重启 NapCat：

```bash
docker restart napcat
```

> **注意：** 如果 astrbot 和 napcat 不在同一宿主机或没有共享目录，需保持 `download_dir` 在两边都能访问的路径下。

---

## 配置项

在 AstrBot WebUI 插件配置页面设置，或直接编辑配置文件：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `download_dir` | `/AstrBot/data/jmcomic/` | 图片下载和 PDF 输出目录 |
| `max_concurrent` | `1` | 同时下载任务数 |
| `auto_clean` | `true` | 完成后自动删除临时文件 |
| `bot_uin` | `1000000` | 合并转发卡片中显示为发送者的 QQ |
| `bot_name` | `"JMComic"` | 合并转发卡片中显示的名称 |
| `batch_size` | `30` | 每批发送的图片数（回退到图片模式时） |
| `allow_groups` | `[]` | 群白名单，空为不限制 |
| `allow_users` | `[]` | 用户白名单，空为不限制 |
| `failed_placeholder` | (插件目录) | 下载失败时填补的占位图路径 |

---

## 工作流程

```
发命令 → 搜索/解析本子 ID → 逐章下载图片
    → jmcomic Feature.export_pdf 生成 PDF
    → OneBot API 发文件到私聊
    → 用消息 ID 构造合并转发节点
    → 群聊展示合并转发卡片
    → 清理临时文件
```

## 依赖

- [jmcomic](https://github.com/hect0x7/JMComic-Crawler-Python) >= 2.6.0
- AstrBot >= v4.25
- NapCat (或兼容 OneBot v11 的客户端)

## License

MIT
