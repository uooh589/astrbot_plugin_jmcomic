"""
JMComic (禁漫天堂) Download Plugin for AstrBot

Based on JMComic-Crawler-Python (https://github.com/hect0x7/JMComic-Crawler-Python)
"""

import os
import re
import asyncio
import logging
import functools
import random
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, List, Tuple

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register

import jmcomic
from jmcomic import JmOption, JmAlbumDetail, Feature
from jmcomic.jm_exception import PartialDownloadFailedException

logger = logging.getLogger(__name__)

_PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))

CATEGORY_HELP = """搜索关键词参考:

常用标签:
  doujin  - 同人
  hanman  - 韩漫
  single  - 单本
  short   - 短篇
  meiman  - 美漫
  3D      - 3D
  another - 其他

排序:
  mr - 最新发布 (默认)  mv - 最多观看
  tf - 最多爱心        md - 最多评论

时间:
  a - 全部 (默认)  t - 今日  w - 本周  m - 本月"""

_RANK_KEYS = ("周榜", "日榜", "月榜")
_RANK_LABELS = {"周榜": "周", "日榜": "日", "月榜": "月"}


@register("astrbot_plugin_jmcomic", "contributor",
          "JMComic 禁漫天堂下载插件 - 搜索、下载、PDF转换、排行榜",
          "1.0.0")
class JmcomicPlugin(Star):
    def __init__(self, context: Context, config: dict = None):
        super().__init__(context)
        self.config = config or {}

        shared_base = "/AstrBot/data/jmcomic"
        self.download_dir = self.config.get("download_dir", shared_base)

        self.allow_groups = self.config.get("allow_groups", [])
        self.allow_users = self.config.get("allow_users", [])
        self.max_concurrent = self.config.get("max_concurrent", 1)
        self.auto_clean = self.config.get("auto_clean", True)

        fp = os.path.join(_PLUGIN_DIR, "failed_placeholder.jpg")
        self.failed_placeholder = self.config.get("failed_placeholder", fp)

        self.jmcomic_config = self.config.get("jmcomic_config", {})

        self._executor = ThreadPoolExecutor(max_workers=self.max_concurrent + 1)
        self._semaphore = asyncio.Semaphore(self.max_concurrent)
        self._pending_confirm: dict = {}
        self._confirm_lock = asyncio.Lock()
        self._cancel_events: dict = {}
        self._cancel_lock = asyncio.Lock()

    def __del__(self):
        self._executor.shutdown(wait=False)

    # ── JMComic Option ─────────────────────────────────────

    def _get_jm_option(self, base_dir: str = None) -> JmOption:
        opt = JmOption.default_dict()
        opt["dir_rule"]["base_dir"] = base_dir or self.download_dir
        opt["dir_rule"]["rule"] = "Bd_Aid_Pid"

        opt.setdefault("download", {})
        opt["download"]["cache"] = True
        opt["download"].setdefault("image", {})
        opt["download"]["image"]["suffix"] = ".jpg"
        opt["download"]["image"]["batch_count"] = 30
        opt["download"].setdefault("threading", {})
        opt["download"]["threading"]["image"] = self.jmcomic_config.get("threading_image", 10)
        opt["download"]["threading"]["photo"] = self.jmcomic_config.get("threading_photo", 2)

        opt.setdefault("client", {})
        opt["client"]["impl"] = "api"
        opt["client"]["cache"] = True

        if "proxies" in self.jmcomic_config:
            opt["client"]["postman"] = {
                "type": "curl_cffi",
                "meta_data": {"impersonate": "chrome", "proxies": self.jmcomic_config["proxies"]},
            }
        if "domains" in self.jmcomic_config:
            opt["client"]["domain"] = self.jmcomic_config["domains"]
        opt.pop("log", None)
        return JmOption(**opt)

    # ── Permission ─────────────────────────────────────────

    def _check_permission(self, event: AstrMessageEvent) -> bool:
        if not self.allow_groups and not self.allow_users:
            return True
        group_id = getattr(event, "group_id", None) or getattr(getattr(event, "message_obj", None), "group_id", None)
        user_id = event.get_sender_id()
        if self.allow_groups and group_id and str(group_id) in [str(x) for x in self.allow_groups]:
            return True
        if self.allow_users and str(user_id) in [str(x) for x in self.allow_users]:
            return True
        return False

    @staticmethod
    def _get_command_args(event: AstrMessageEvent) -> str:
        text = re.sub(r"^@\S+\s+", "", event.message_str.strip())
        parts = text.split(maxsplit=1)
        return parts[1].strip() if len(parts) > 1 else ""

    def _help_text(self) -> str:
        p = self.config.get("command_prefix", "/")
        return (
            "JMComic 禁漫插件 v1.0.0\n\n"
            f"{p}jm <ID/名称>     - 下载本子\n"
            f"{p}jm author:名称    - 搜索作者下载\n"
            f"{p}jm 周榜/日榜/月榜  - 查看排行\n"
            f"{p}jm cancel        - 取消下载\n"
            f"{p}jm help/log      - 帮助/更新日志\n"
            f"{p}jmv <ID/关键词>   - 查看详情\n"
            f"{p}jmr [分类/排行]   - 随机本子\n"
            f"{p}jmr author:名称   - 作者随机\n"
            f"{p}jml              - 搜索参考"
        )

    CHANGELOG = """更新日志 v1.0.0
- /jm 下载（ID/名称/作者）
- /jmv 详情（ID/关键词）
- /jmr 随机（标签/排行/作者）
- PDF导出 + 合并转发
- 私聊发文件，群聊卡片
- /jm cancel 取消下载"""

    # ── Sync helpers (run in thread pool) ──────────────────

    def _get_album_detail_sync(self, album_id: str) -> Optional[JmAlbumDetail]:
        opt = self._get_jm_option()
        for impl in ("html", "api"):
            try:
                return opt.new_jm_client(impl=impl).get_album_detail(album_id)
            except Exception:
                continue
        return None

    def _search_album_sync(self, query: str) -> Optional[JmAlbumDetail]:
        opt = self._get_jm_option()
        client = opt.new_jm_client()

        if query.startswith(("author:", "作者:")):
            aname = query.split(":", 1)[1].strip()
            if aname:
                page = client.search_author(search_query=aname, page=1)
                items = list(page)
                return client.get_album_detail(items[0][0]) if items else None
            return None

        if query.isdigit():
            try:
                return client.get_album_detail(query)
            except Exception:
                pass

        page = client.search_site(search_query=query, page=1, order_by="mr", time="a", category="0")
        items = list(page)
        return client.get_album_detail(items[0][0]) if items else None

    def _fetch_ranking_sync(self, rank_type: str) -> List[Tuple[str, str]]:
        opt = self._get_jm_option()
        client = opt.new_jm_client()
        if rank_type == "周榜":
            return list(client.week_ranking(page=1))
        if rank_type == "日榜":
            return list(client.day_ranking(page=1))
        if rank_type == "月榜":
            return list(client.month_ranking(page=1))
        return []

    def _fetch_random_pool_sync(self, tag: str) -> List[Tuple[str, str]]:
        opt = self._get_jm_option()
        client = opt.new_jm_client()

        if tag.startswith(("author:", "作者:")):
            aname = tag.split(":", 1)[1].strip()
            if aname:
                return list(client.search_author(search_query=aname, page=1))
            return []
        if tag:
            return list(client.search_site(search_query=tag, page=1, order_by="mr", time="a", category="0"))
        return list(client.categories_filter(page=random.randint(1, 50), time="a", category="0", order_by="mr"))

    def _fill_missing_images(self, image_dir: str):
        if not os.path.isdir(image_dir) or not os.path.isfile(self.failed_placeholder):
            return
        files = [f for f in os.listdir(image_dir) if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))]
        if not files:
            return
        seen = set()
        for f in files:
            m = re.match(r"(\d+)", f)
            if m:
                seen.add(int(m.group(1)))
        if not seen:
            return
        missing = sorted(set(range(1, max(seen) + 1)) - seen)
        if not missing:
            return
        logger.info("Filling %d missing images in %s", len(missing), image_dir)
        for p in missing:
            dst = os.path.join(image_dir, f"{p:05d}.jpg")
            try:
                shutil.copy2(self.failed_placeholder, dst)
            except Exception as e:
                logger.warning("fill %s: %s", dst, e)

    def _download_chapters_sync(self, album: JmAlbumDetail, work_dir: str,
                                  cancel_event: threading.Event = None) -> List[dict]:
        """Download per-chapter and generate per-chapter PDFs. [{title, pdf_path, photo_id}]"""
        opt = self._get_jm_option(base_dir=work_dir)
        chapters = []

        episodes = album.episode_list or [(album.album_id, None, album.name, "")]
        for ep in episodes:
            if cancel_event and cancel_event.is_set():
                logger.info("Download cancelled by user")
                break
            photo_id = ep[0]
            photo_title = ep[2] if len(ep) >= 3 else f"第{len(chapters) + 1}话"

            # Pass 1: download images
            try:
                opt.download_photo(photo_id)
            except PartialDownloadFailedException as e:
                logger.warning("Chapter %s partial failure: %s", photo_id, e)

            # Fill gaps
            ch_dir = os.path.join(work_dir, album.album_id, str(photo_id))
            self._fill_missing_images(ch_dir)

            # Pass 2: generate PDF (cache hit, doesn't re-download)
            extra = Feature.export_pdf(pdf_dir=work_dir, filename_rule="Pid", delete_original_file=True)
            opt.download_photo(photo_id, extra=extra)

            pdf_path = os.path.join(work_dir, f"{photo_id}.pdf")
            if not os.path.isfile(pdf_path):
                logger.warning("PDF not generated for chapter %s", photo_id)
                continue
            chapters.append({"title": photo_title, "pdf_path": pdf_path, "photo_id": str(photo_id)})

        return chapters

    # ── Sync bridge ────────────────────────────────────────

    async def _run_sync(self, func, *args, timeout=600, **kwargs):
        loop = asyncio.get_event_loop()
        return await asyncio.wait_for(
            loop.run_in_executor(self._executor, functools.partial(func, *args, **kwargs)),
            timeout=timeout,
        )

    # ── Send PDFs via merge-forward ───────────────────────

    async def _send_pdfs_forward(self, event: AstrMessageEvent, chapters: List[dict], album_title: str):
        """Send each chapter's PDF as a forward node. Errors on one chapter don't skip others."""
        group_id = getattr(event.message_obj, "group_id", None)
        user_id = event.get_sender_id()
        bot = getattr(event, "bot", None)
        if not group_id or not bot:
            logger.error("Cannot send: no group_id or bot")
            return

        for ch in chapters:
            pdf_path = ch.get("pdf_path")
            if not pdf_path or not os.path.isfile(pdf_path):
                continue

            try:
                file_name = f"document_{ch['photo_id']}.pdf"
                file_seg = [{"type": "file", "data": {"file": pdf_path, "name": file_name}}]

                try:
                    msg_resp = await bot.call_action("send_private_msg", user_id=int(user_id), message=file_seg)
                except Exception:
                    msg_resp = await bot.call_action("send_group_msg", group_id=group_id, message=file_seg)

                if not msg_resp:
                    continue
                msg_id = msg_resp.get("message_id") if isinstance(msg_resp, dict) else None
                if not msg_id:
                    continue

                fwd = await bot.call_action(
                    "send_group_forward_msg", group_id=group_id,
                    messages=[{"type": "node", "data": {"id": int(msg_id)}}],
                )

                if isinstance(fwd, dict) and fwd.get("res_id"):
                    try:
                        await bot.call_action("delete_msg", message_id=int(msg_id))
                    except Exception:
                        pass
                else:
                    logger.warning("Forward may have been blocked for %s", ch["title"])
            except Exception as e:
                logger.error("Failed to send %s: %s", ch["title"], e)

    # ── File cleanup ───────────────────────────────────────

    def _cleanup_files(self, work_dir: str):
        try:
            if os.path.isdir(work_dir):
                shutil.rmtree(work_dir, ignore_errors=True)
        except Exception as e:
            logger.warning("Cleanup error: %s", e)

    # ── Command Handlers ───────────────────────────────────

    @filter.command("jm")
    async def handle_jm(self, event: AstrMessageEvent):
        if not self._check_permission(event):
            yield event.plain_result("你没有权限使用此命令。")
            return

        args = self._get_command_args(event)

        if not args or args in ("help", "h", "帮助"):
            yield event.plain_result(self._help_text())
            return
        if args in ("log", "更新日志", "changelog"):
            yield event.plain_result(self.CHANGELOG)
            return
        if args in ("cancel", "取消"):
            uid = event.get_sender_id()
            async with self._cancel_lock:
                e = self._cancel_events.pop(uid, None)
                if e:
                    e.set()
                    yield event.plain_result("已取消下载。")
                else:
                    yield event.plain_result("没有正在下载的任务。")
            return
        if args in _RANK_KEYS:
            yield event.plain_result(f"正在获取{args}...")
            try:
                rankings = await self._run_sync(self._fetch_ranking_sync, args)
                if not rankings:
                    yield event.plain_result("暂无排行数据。")
                    return
                label = _RANK_LABELS.get(args, "")
                lines = [f"━━ JM{label}榜 Top 15 ━━", ""]
                for i, (aid, atitle) in enumerate(rankings[:15], 1):
                    lines.append(f"{i}. [{aid}] {atitle}")
                yield event.plain_result("\n".join(lines))
            except Exception as e:
                logger.exception("Ranking failed")
                yield event.plain_result(f"获取排行榜失败: {e}")
            return

        async for result in self._download_and_send(event, args):
            yield result

    @filter.command("jmr")
    async def handle_jmr(self, event: AstrMessageEvent):
        if not self._check_permission(event):
            yield event.plain_result("你没有权限使用此命令。")
            return
        tag = self._get_command_args(event)

        if tag in _RANK_KEYS:
            yield event.plain_result(f"正在从{tag}随机抽取...")
            try:
                r2 = await self._run_sync(self._fetch_ranking_sync, tag)
                if not r2:
                    yield event.plain_result("暂无排行数据。")
                    return
                aid, t2 = random.choice(r2)
                yield event.plain_result(f"抽中《{t2}》({aid})")
                async for r3 in self._download_and_send(event, str(aid)):
                    yield r3
            except Exception as e:
                logger.exception("Random ranking failed")
                yield event.plain_result(f"随机获取失败: {e}")
            return

        yield event.plain_result(f"正在随机抽取{'〈' + tag + '〉' if tag else '本子'}...")
        try:
            pool = await self._run_sync(self._fetch_random_pool_sync, tag)
            if not pool:
                yield event.plain_result("未找到可用的本子。")
                return
            aid, t2 = random.choice(pool)
            yield event.plain_result(f"抽中《{t2}》({aid})")
            async for r3 in self._download_and_send(event, str(aid)):
                yield r3
        except Exception as e:
            logger.exception("Random failed")
            yield event.plain_result(f"随机获取失败: {e}")

    @filter.command("jmv")
    async def handle_jmv(self, event: AstrMessageEvent):
        if not self._check_permission(event):
            yield event.plain_result("你没有权限使用此命令。")
            return
        args = self._get_command_args(event)
        if not args:
            yield event.plain_result("用法: /jmv <本子ID|作者:名称|关键词>")
            return

        try:
            if args.isdigit():
                yield event.plain_result(f"正在查询本子 [{args}]...")
                album = await self._run_sync(self._get_album_detail_sync, args)
            else:
                yield event.plain_result(f"正在搜索「{args}」...")
                album = await self._run_sync(self._search_album_sync, args)
        except Exception as e:
            yield event.plain_result(f"查询失败: {e}")
            return

        if not album:
            yield event.plain_result("未找到该本子。" if args.isdigit() else f"未找到「{args}」相关本子。")
            return

        lines = [f"━━ {album.title} ━━"]
        lines.append(f"  🆔 ID:    JM{album.album_id}")
        lines.append(f"  ✍️ 作者:  {album.author}")
        lines.append(f"  📄 页数:  {album.page_count}")
        for k, v in [("❤️ 点赞", album.likes), ("👀 观看", album.views), ("💬 评论", album.comment_count)]:
            if v:
                lines.append(f"  {k}:  {v}")
        lines.append(f"  📅 发布:  {album.pub_date}")
        if album.update_date:
            lines.append(f"  📅 更新:  {album.update_date}")
        if album.tags:
            t = album.tags if isinstance(album.tags, list) else [album.tags]
            lines.append(f"  🏷️ 标签:  {' | '.join(str(x) for x in t[:10])}")
        if album.actors:
            lines.append(f"  🎭 人物:  {' | '.join(str(a) for a in album.actors[:8])}")
        if album.works:
            lines.append(f"  📚 作品:  {' | '.join(str(w) for w in album.works[:5])}")
        if album.episode_list:
            lines.append(f"  📑 章节 ({len(album.episode_list)}):")
            for i, ep in enumerate(album.episode_list, 1):
                t = ep[2] if len(ep) >= 3 else f"第{i}话"
                lines.append(f"    {i}. {t}  (id: {ep[0]})")
        yield event.plain_result("\n".join(lines) + "\n💡 /jm <ID> 下载")

    @filter.command("jml")
    async def handle_jml(self, event: AstrMessageEvent):
        if not self._check_permission(event):
            yield event.plain_result("你没有权限使用此命令。")
            return
        yield event.plain_result(CATEGORY_HELP)

    # ── Core download & PDF pipeline ───────────────────────

    async def _download_and_send(self, event: AstrMessageEvent, query: str):
        """Full pipeline: resolve → download → send → cleanup."""
        async with self._semaphore:
            try:
                album = await self._run_sync(self._search_album_sync, query)
            except Exception as e:
                yield event.plain_result(f"搜索失败: {e}")
                return

            if album is None:
                yield event.plain_result(f"未找到《{query}》相关本子。")
                return

            album_id = album.album_id
            title = album.title

            # Large-album confirmation (>100 pages)
            pc = album.page_count
            if pc > 100:
                uid = event.get_sender_id()
                ckey = f"{uid}:{album_id}"
                async with self._confirm_lock:
                    if self._pending_confirm.get(ckey) != True:
                        self._pending_confirm[ckey] = True
                        yield event.plain_result(
                            f"《{title}》共 {pc} 页（超过100页），再次发送相同命令确认下载。"
                        )
                        return
                    del self._pending_confirm[ckey]

            yield event.plain_result(f"正在下载《{title}》...")

            work_dir = os.path.join(self.download_dir, f"tmp_{album_id}")
            cancel_event = threading.Event()
            uid = event.get_sender_id()
            async with self._cancel_lock:
                self._cancel_events[uid] = cancel_event

            cleanup_cancel = True
            try:
                chapters = await self._run_sync(
                    self._download_chapters_sync, album, work_dir, cancel_event,
                )
            except Exception as e:
                logger.exception("Download failed for %s", album_id)
                self._cleanup_files(work_dir)
                yield event.plain_result(f"下载失败: {e}")
                return
            finally:
                async with self._cancel_lock:
                    self._cancel_events.pop(uid, None)
                cleanup_cancel = False

            if not chapters:
                self._cleanup_files(work_dir)
                yield event.plain_result("未生成PDF文件。")
                return

            try:
                await self._send_pdfs_forward(event, chapters, title)
            except Exception as e:
                logger.exception("Send failed")
                yield event.plain_result(f"发送失败: {e}")

            if self.auto_clean:
                self._cleanup_files(work_dir)
