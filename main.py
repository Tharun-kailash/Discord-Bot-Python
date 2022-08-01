import os
import discord


from discord.ext import commands


class MainBot(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        print("main init")

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'Logged in as {self.bot.user} ({self.bot.user.id})')
        print("listenet on_ready")
        await bot.change_presence(status=discord.Status.idle)

    @commands.Cog.listener()
    async def on_resumed(self):
        print('Bot has reconnected!')

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        print("Listener on command error")
        await ctx.send(error)
        if isinstance(error, commands.CommandNotFound):
            await ctx.send('**Invalid Command!**')
        elif isinstance(error, commands.MissingPermissions):
            await ctx.send('**Bot Permission Missing!**')

intents = discord.Intents.default()
intents.members = True
intents.presences = True

bot = commands.Bot(command_prefix=commands.when_mentioned_or('/'),description='Create Your Own Vibe', intents=intents)

for filename in os.listdir('./commands'):
    if filename.endswith('.py'):
        bot.load_extension(f'commands.{filename[: -3]}')

bot.add_cog(MainBot(bot))
bot.run('OTIzMTE5ODg5NTQ2MzYyODgw.YcLYZA.mk8GzDi3X-DN6qLb0OoO8nK5LQI', reconnect=True)
