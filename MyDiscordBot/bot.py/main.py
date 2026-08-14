import discord
from discord.ext import commands
from discord.ui import Button, View, Modal, TextInput
import sqlite3
from datetime import datetime
import os

# ==================== [ إعدادات البوت وقاعدة البيانات ] ====================
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

conn = sqlite3.connect("family_system.db")
cursor = conn.cursor()

# جداول التاسكات والإنذارات
cursor.execute('''
CREATE TABLE IF NOT EXISTS user_tasks (
    user_id INTEGER PRIMARY KEY,
    weed_plants INTEGER DEFAULT 0,
    total_submissions INTEGER DEFAULT 0
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS warnings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    mod_id INTEGER,
    reason TEXT,
    date TEXT
)
''')
conn.commit()

# ==================== [ إعدادات العائلة ] ====================
ADMIN_ROLE_ID = 1537674395366064229  # رول إدارة العائلة
WEEKLY_TARGET_GOAL = 10000          # التاركت الأسبوعي للعائلة (10,000 وحدة حشيش)

COLOR_NAVY = discord.Color.from_rgb(11, 19, 43)
COLOR_BROWN = discord.Color.from_rgb(89, 52, 20)
COLOR_GOLD = discord.Color.from_rgb(212, 175, 55)
COLOR_RED = discord.Color.from_rgb(180, 40, 40)

target_message_info = {"channel_id": None, "message_id": None}

# ==================== [ دالة تحديث شريط التاركت ] ====================
async def update_target_embed(guild):
    if not target_message_info["channel_id"] or not target_message_info["message_id"]:
        return
    try:
        channel = guild.get_channel(target_message_info["channel_id"])
        if not channel: return
        msg = await channel.fetch_message(target_message_info["message_id"])
        
        cursor.execute("SELECT SUM(weed_plants) FROM user_tasks")
        result = cursor.fetchone()[0]
        total_weed = result if result else 0

        percentage = min(100.0, (total_weed / WEEKLY_TARGET_GOAL) * 100)
        filled = int(percentage // 10)
        bar = "▓" * filled + "░" * (10 - filled)

        total_cost = (total_weed / 500) * 36960

        embed = discord.Embed(
            title="🎯 │ هَدَفُ العَائِلَةِ الأُسْبُوعِيِّ (GANG TARGET)",
            description=(
                f"**شريط الإنجاز الحالي:**\n"
                f"`[{bar}]` **{percentage:.1f}%**\n\n"
                f"• **إجمالي المسلَّم:** `{total_weed:,}` / `{WEEKLY_TARGET_GOAL:,}` وحدة حشيش\n"
                f"• **المتبقي للهدف:** `{max(0, WEEKLY_TARGET_GOAL - total_weed):,}` وحدة\n"
                f"• **إجمالي قيمة الموارد المسلّمة:** `${total_cost:,.0f}`"
            ),
            color=COLOR_GOLD,
            timestamp=datetime.now()
        )
        embed.set_footer(text="يتحدث تلقائياً مع كل تسليم جديد 🔄")
        await msg.edit(embed=embed)
    except Exception as e:
        print(f"Error updating target embed: {e}")

# ==================== [ شاشة تسليم التاسك (Modal) ] ====================

class TaskSubmissionModal(Modal, title="📦 تسليم تاسك للعائلة"):
    player_id = TextInput(
        label="1. ID اللاعب أو معرفه (Discord ID / Mention)",
        style=discord.TextStyle.short,
        placeholder="مثال: 1234567890 أو @Youssef",
        required=True
    )
    task_type = TextInput(
        label="2. نوع التاسك",
        style=discord.TextStyle.short,
        placeholder="اكتب: حشيش",
        default="حشيش",
        required=True
    )
    quantity = TextInput(
        label="3. الكمية المسلّمة (عدد الزرعات)",
        style=discord.TextStyle.short,
        placeholder="المطلوب الأساسي: 500 زرعة",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        has_permission = any(role.id == ADMIN_ROLE_ID for role in interaction.user.roles) or interaction.user.guild_permissions.administrator
        if not has_permission:
            await interaction.response.send_message("❌ عفواً! فقط مسؤولين الموارد هم من يستطيعون تسجيل التاسكات.", ephemeral=True)
            return

        try:
            qty = int(self.quantity.value)
        except ValueError:
            await interaction.response.send_message("❌ يرجى كتابة الكمية كأرقام فقط.", ephemeral=True)
            return

        clean_id = self.player_id.value.replace("<@", "").replace(">", "").replace("!", "").strip()
        try:
            target_user_id = int(clean_id)
            target_user = interaction.guild.get_member(target_user_id)
        except ValueError:
            target_user = None

        user_mention = target_user.mention if target_user else self.player_id.value

        if target_user:
            cursor.execute('''
                INSERT INTO user_tasks (user_id, weed_plants, total_submissions)
                VALUES (?, ?, 1)
                ON CONFLICT(user_id) DO UPDATE SET
                weed_plants = weed_plants + ?,
                total_submissions = total_submissions + 1
            ''', (target_user.id, qty, qty))
            conn.commit()

        percentage = (qty / 500) * 100
        cost_calculated = (qty / 500) * 36960

        status_text = "✅ مكتمل بالكامل"
        if percentage > 100:
            status_text = f"🔥 متفوق! (سَلَّم زيادة {qty - 500} زرعة)"
        elif percentage < 100:
            status_text = f"⚠️ غير مكتمل (متبقي {500 - qty} زرعة)"

        embed = discord.Embed(
            title="📜 │ سِجِلُّ تَسْلِيمِ التَّاسْكَاتِ الرَّسْمِيِّ",
            color=COLOR_BROWN,
            timestamp=datetime.now()
        )
        embed.add_field(
            name="🆔 ─── [ بَيَانَاتُ اللاَّعِبِ ] ───",
            value=f"• **اللاعب:** {user_mention}\n• **المسؤول الموثِّق:** {interaction.user.mention}",
            inline=False
        )
        embed.add_field(
            name="📦 ─── [ تَفَاصِيلُ التَّسْلِيمِ ] ───",
            value=(
                f"• **نوع التاسك:** `{self.task_type.value}`\n"
                f"• **الكمية المسلمة:** `{qty}` زرعة\n"
                f"• **نسبة الإنجاز:** `{percentage:.1f}%`\n"
                f"• **التكلفة التقديرية:** `${cost_calculated:,.0f}`\n"
                f"• **الحالة:** {status_text}"
            ),
            inline=False
        )
        if interaction.guild.icon:
            embed.set_footer(text="نظام إدارة الموارد - TOGAR", icon_url=interaction.guild.icon.url)

        await interaction.response.send_message(embed=embed)
        await update_target_embed(interaction.guild)

class TaskPanelView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="تسجيل تسليم تاسك 📥", style=discord.ButtonStyle.success, custom_id="submit_task_btn")
    async def submit_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(TaskSubmissionModal())

# ==================== [ أوامر البوت ] ====================

@bot.event
async def on_ready():
    print(f"✅ تم تشغيل البوت بنجاح باسم: {bot.user.name}")
    bot.add_view(TaskPanelView())

@bot.command(name="setup_task")
@commands.has_permissions(administrator=True)
async def setup_task(ctx):
    embed = discord.Embed(
        title="🌿 │ مَكْتَبُ تَسْلِيمِ التَّاسْكَاتِ وَالمَوَارِدِ",
        description=(
            "**خاص بمؤولي الموارد وإدارة العائلة.**\n\n"
            "اضغط على الزر بالأسفل لتسجيل تسليم تاسك جديد لأحد الأعضاء.\n"
            "📌 **تاسك الحشيش المعتمد (500 زرعة):**\n"
            "• Seeds: 84 | Pots: 84 | Soil: 84 | Water: 252 | Cola: 504\n"
            "• **التكلفة الكلية:** `$36,960`"
        ),
        color=COLOR_NAVY
    )
    await ctx.send(embed=embed, view=TaskPanelView())
    try: await ctx.message.delete()
    except: pass

@bot.command(name="setup_target")
@commands.has_permissions(administrator=True)
async def setup_target(ctx):
    embed = discord.Embed(
        title="🎯 │ هَدَفُ العَائِلَةِ الأُسْبُوعِيِّ (GANG TARGET)",
        description="جاري تحميل بيانات التاركت الأسبوعي...",
        color=COLOR_GOLD
    )
    msg = await ctx.send(embed=embed)
    target_message_info["channel_id"] = ctx.channel.id
    target_message_info["message_id"] = msg.id
    await update_target_embed(ctx.guild)
    try: await ctx.message.delete()
    except: pass

@bot.command(name="warn")
@commands.has_permissions(administrator=True)
async def warn_user(ctx, member: discord.Member, *, reason="عدم الالتزام بالقوانين أو التاسك"):
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    cursor.execute("INSERT INTO warnings (user_id, mod_id, reason, date) VALUES (?, ?, ?, ?)",
                   (member.id, ctx.author.id, reason, date_str))
    conn.commit()

    cursor.execute("SELECT COUNT(*) FROM warnings WHERE user_id = ?", (member.id,))
    warn_count = cursor.fetchone()[0]

    embed = discord.Embed(
        title="⚠️ │ إِشْعَارُ إنْذَارٍ جَدِيدٍ",
        description=f"تم إعطاء إنذار لـ {member.mention}",
        color=COLOR_RED
    )
    embed.add_field(name="السبب", value=f"`{reason}`", inline=False)
    embed.add_field(name="عدد الإنذارات الحالي", value=f"`{warn_count} / 3`", inline=True)
    embed.add_field(name="المسؤول", value=ctx.author.mention, inline=True)

    if warn_count >= 3:
        embed.add_field(
            name="🚨 عقوبة حاسمة!",
            value="**وصل العضو للحد الأقصى للإنذارات (3/3)!**",
            inline=False
        )

    await ctx.send(embed=embed)

@bot.command(name="warnings")
async def show_warnings(ctx, member: discord.Member = None):
    target = member or ctx.author
    cursor.execute("SELECT reason, date FROM warnings WHERE user_id = ?", (target.id,))
    warns = cursor.fetchall()

    if not warns:
        await ctx.send(f"✅ {target.mention} ليس لديه أي إنذارات مسجلة.")
        return

    embed = discord.Embed(
        title=f"📜 │ سِجِلُّ إنْذَارَاتِ: {target.display_name}",
        description=f"إجمالي الإنذارات: `{len(warns)}`",
        color=COLOR_RED
    )
    for idx, (reason, date) in enumerate(warns, start=1):
        embed.add_field(name=f"إنذار #{idx} - ({date})", value=f"• السبب: `{reason}`", inline=False)

    await ctx.send(embed=embed)

@bot.command(name="clearwarns")
@commands.has_permissions(administrator=True)
async def clear_warnings(ctx, member: discord.Member):
    cursor.execute("DELETE FROM warnings WHERE user_id = ?", (member.id,))
    conn.commit()
    await ctx.send(f"✅ تم مسح جميع إنذارات {member.mention} بنجاح.")

@bot.command(name="announce")
@commands.has_permissions(administrator=True)
async def announce(ctx, title: str, *, content: str):
    embed = discord.Embed(
        title=f"📢 │ {title}",
        description=content,
        color=COLOR_NAVY,
        timestamp=datetime.now()
    )
    embed.set_footer(text="إعلان رسمي صادر من إدارة العائلة")
    await ctx.send("@everyone", embed=embed)
    try: await ctx.message.delete()
    except: pass

# ==================== [ تشغيل البوت ] ====================
bot.run("MTUzNzY2NzYwMDAxNDc3ODQ4OA.GaNy9M.wZdgoxNhAXlNc6sJCTPK6b2kGDFr5y2y7q3fQM")