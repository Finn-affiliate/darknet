import discord
from discord.ext import commands

TOKEN = "DEIN_SETUP_BOT_TOKEN"

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Setup Bot online als {bot.user}")
    print("Tippe !setup im Server um zu starten")

@bot.command()
@commands.has_permissions(administrator=True)
async def setup(ctx):
    guild = ctx.guild
    msg = await ctx.send("⚙️ Richte Server ein...")

    # Alle bestehenden Channels löschen
    for channel in guild.channels:
        try:
            await channel.delete()
        except:
            pass

    # Rollen erstellen
    everyone = guild.default_role
    await everyone.edit(permissions=discord.Permissions.none())

    mitglied_rolle = await guild.create_role(
        name="Mitglied",
        color=discord.Color.dark_red(),
        mentionable=False
    )

    admin_rolle = await guild.create_role(
        name="Admin",
        color=discord.Color.gold(),
        permissions=discord.Permissions.all(),
        mentionable=False
    )

    # Permissions definieren
    everyone_deny = discord.PermissionOverwrite(
        read_messages=False,
        send_messages=False
    )
    mitglied_allow = discord.PermissionOverwrite(
        read_messages=True,
        send_messages=True
    )
    mitglied_readonly = discord.PermissionOverwrite(
        read_messages=True,
        send_messages=False
    )
    admin_allow = discord.PermissionOverwrite(
        read_messages=True,
        send_messages=True,
        manage_messages=True
    )

    # Kategorien + Channels erstellen
    # ── UNTERGRUND ──
    cat_markt = await guild.create_category("🕶️ UNTERGRUND", overwrites={
        everyone: everyone_deny,
        mitglied_rolle: discord.PermissionOverwrite(read_messages=True)
    })

    schwarzmarkt = await guild.create_text_channel("schwarzmarkt", category=cat_markt, overwrites={
        everyone: everyone_deny,
        mitglied_rolle: mitglied_readonly,
        admin_rolle: admin_allow
    }, topic="Illegale Waren & Angebote")

    auftraege = await guild.create_text_channel("auftraege", category=cat_markt, overwrites={
        everyone: everyone_deny,
        mitglied_rolle: mitglied_readonly,
        admin_rolle: admin_allow
    }, topic="Anonyme Aufträge")

    kopfgelder = await guild.create_text_channel("kopfgelder", category=cat_markt, overwrites={
        everyone: everyone_deny,
        mitglied_rolle: mitglied_readonly,
        admin_rolle: admin_allow
    }, topic="Aktive Kopfgelder")

    befehle = await guild.create_text_channel("befehle", category=cat_markt, overwrites={
        everyone: everyone_deny,
        mitglied_rolle: mitglied_allow,
        admin_rolle: admin_allow
    }, topic="Hier deine Commands eingeben")

    # ── ADMIN ──
    cat_admin = await guild.create_category("🔒 ADMIN", overwrites={
        everyone: everyone_deny,
        mitglied_rolle: everyone_deny,
        admin_rolle: admin_allow
    })

    admin_log = await guild.create_text_channel("admin-log", category=cat_admin, overwrites={
        everyone: everyone_deny,
        mitglied_rolle: everyone_deny,
        admin_rolle: admin_allow
    }, topic="Privater Admin Log")

    # Admin Rolle dem Bot-Owner geben
    owner = guild.owner
    await owner.add_roles(admin_rolle)

    # Ergebnis ausgeben
    result = f"""
✅ **Server eingerichtet!**

**Rollen:**
- {mitglied_rolle.mention} – für freigeschaltete Spieler
- {admin_rolle.mention} – nur du (bereits zugewiesen)

**Channel IDs für darknet_bot.py:**
```
CH_SCHWARZMARKT = {schwarzmarkt.id}
CH_AUFTRAEGE    = {auftraege.id}
CH_KOPFGELDER   = {kopfgelder.id}
CH_LOG          = {admin_log.id}
```

📋 Kopiere diese IDs in deinen `darknet_bot.py` und du bist fertig!
Danach kannst du diesen Setup-Bot kicken.
"""
    await admin_log.send(result)
    await msg.edit(content="✅ Fertig! Check den `admin-log` Channel.")

bot.run(TOKEN)
