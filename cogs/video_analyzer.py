"""
Listener automático de videos — analiza metadatos forenses.
"""
import discord
from discord.ext import commands
import asyncio

from cogs.catfish_config import is_monitored, get_log_channel_id
from database.db import get_user, upsert_user, update_score
from services.video_metadata import analyze_video

SCORE_TIMESTAMPS_ZERO = 15
SCORE_SHORT_CLIP = 10


class VideoAnalyzerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
        if not message.attachments:
            return
        if not is_monitored(message.channel.id):
            return

        for att in message.attachments:
            if not att.content_type:
                continue
            if not att.content_type.startswith("video/"):
                continue
            if att.size > 25 * 1024 * 1024:
                continue

            try:
                video_bytes = await att.read()
                results = await asyncio.to_thread(analyze_video, video_bytes)

                if not results["suspicious"]:
                    continue

                # Calcular score
                score_add = 0
                if results["timestamps_zero"]:
                    score_add += SCORE_TIMESTAMPS_ZERO
                if results["duration"] > 0 and results["duration"] < 5:
                    score_add += SCORE_SHORT_CLIP

                if score_add == 0:
                    continue

                # Actualizar usuario
                upsert_user(message.author.id, str(message.author),
                    account_created=message.author.created_at.isoformat())
                existing = get_user(message.author.id)
                old_score = existing["score"] if existing else 0
                new_score = old_score + score_add
                update_score(message.author.id, new_score)

                if new_score < 26:
                    continue

                # Alerta
                color = 0xFF0000 if new_score >= 76 else 0xFF8800 if new_score >= 51 else 0xFFCC00
                level = "🔴" if new_score >= 76 else "🟠" if new_score >= 51 else "🟡"

                embed = discord.Embed(
                    title=f"{level} Video sospechoso — Score: {new_score}",
                    color=color,
                )
                embed.set_author(name=f"{message.author} ({message.author.id})",
                    icon_url=message.author.display_avatar.url)

                flags_text = "\n".join(results["flags"]) if results["flags"] else "Sin flags"
                embed.add_field(name="🎬 Análisis de video", value=flags_text, inline=False)
                embed.add_field(name="⏱ Duración", value=f"{results['duration']}s", inline=True)
                embed.add_field(name="📦 Codec", value=results["codec"], inline=True)
                embed.add_field(name="📍 Canal", value=message.channel.mention, inline=True)
                embed.set_footer(text="Anti-Catfish | Video Analysis")

                log_ch_id = get_log_channel_id()
                if log_ch_id:
                    log_ch = message.guild.get_channel(int(log_ch_id))
                    if log_ch:
                        await log_ch.send(embed=embed)

            except Exception as e:
                print(f"[VideoAnalyzer] Error: {e}")


async def setup(bot):
    await bot.add_cog(VideoAnalyzerCog(bot))
