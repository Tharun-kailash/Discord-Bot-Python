from discord.ext import commands
from random import choice

class Utility(commands.Cog):
    def __init__(self, bot):
        print("utility init")
        self.bot = bot

    @commands.command(name='ping',help='This Command return the latency')
    async def ping(self, ctx):
        print("command ping")
        await ctx.send(f'**pong!** Latency: {round(self.bot.latency*1000)}ms')

    @commands.command(name='hello',help='This command returns a random welcome message')
    async def hello(self,ctx):
        print("command hello")
        responses=['***grumble*** Why did you wake me up?','Top of the morning to you lad!','Hello, How are you?','Hi','**Wassup!**']
        await ctx.send(choice(responses))

    @commands.command(name='credits',help='This command returns the credits')
    async def credits(self,ctx):
        print("command credits")
        await ctx.send('Made by Project Mini Project Team')
        await ctx.send('Team Members:\n\t**Prabhu P**\n\t**Tharun Kailash K**\n\t**Vignaraj D**')

def setup(bot):
    print("setup for utility")
    bot.add_cog(Utility(bot))
