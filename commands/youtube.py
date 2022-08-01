from time import *
import discord
from discord import activity
from discord.embeds import Embed
from discord.ext import commands

import asyncio
import itertools
import sys
import traceback
import shelve
import statistics
from async_timeout import timeout
from functools import partial
from random import choice
from youtube_dl import YoutubeDL

log=set({})
emoji_list={'playpause':'\u23EF','stop':'\u23F9','skip':'\u23ED','plus':'🔊','minus':'🔉'}
ytdlopts = {
    'format': 'bestaudio/best',
    'outtmpl': 'downloads/%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0'
}

ffmpegopts = {
    'before_options': '-nostdin',
    'options': '-vn'
}

ytdl = YoutubeDL(ytdlopts)

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials


auth_manager=SpotifyClientCredentials(client_id='0b06f7bea31c4a2982881f0b1cfec5f1',client_secret='74640a5669d94f50afbe2a1114552fde')

sp=spotipy.Spotify(auth_manager=auth_manager)

class VoiceConnectionError(commands.CommandError):
    """Custom Exception class for connection errors."""


class InvalidVoiceChannel(VoiceConnectionError):
    """Exception for cases of invalid Voice Channels."""


class YTDLSource(discord.PCMVolumeTransformer):

    def __init__(self, source, *, data, requester,duration,artist,thumbnail):
        print("ytdl init")
        super().__init__(source)
        self.requester = requester
        self.duration=duration
        self.artist=artist
        self.thumbnail=thumbnail
        self.title = data.get('title')
        self.web_url = data.get('webpage_url')

    def __getitem__(self, item: str):
        """Allows us to access attributes similar to a dict.
        This is only useful when you are NOT downloading.
        """
        print('getitem')
        return self.__getattribute__(item)

    @classmethod
    async def create_source(cls, ctx, search: str, *, loop, download=False):
        print('Create source')
        loop = loop or asyncio.get_event_loop()

        to_run = partial(ytdl.extract_info, url=search, download=download)
        data = await loop.run_in_executor(None, to_run)

        if 'entries' in data:
            data = data['entries'][0]

        await ctx.send(f'[Added {data["title"]} to the Queue.]\n', delete_after=1)
        if download:
            source = ytdl.prepare_filename(data)
        else:
            return {'webpage_url': data['webpage_url'], 'requester': ctx.author, 'title': data['title']}
        
        return cls(discord.FFmpegPCMAudio(source), data=data, requester=ctx.author,duration=data['duration'],artist=data['artist'],thumbnail=data['thumbnail'])

    @classmethod
    async def create_source_playlist(cls, ctx, search: str, *, loop, download=False):
        print("create source playlist")
        loop = loop or asyncio.get_event_loop()
        to_run = partial(ytdl.extract_info, url=search, download=download)
        data = await loop.run_in_executor(None, to_run)
        c=1
        url_list=set()
        for i in data['entries']:
            url_list.add(i['webpage_url'])
        return url_list

    @classmethod
    async def create_suggestion(self,loop):
        print("create suggestion")
        loop = loop or asyncio.get_event_loop()
        shelf=shelve.open('F:\OneDrive\Documents\Python-MProject\Main\data\music_log',flag='r')
        artist=[]
        for i in shelf.keys():
            artist.append(shelf[i]['artist'])
            
        artist_set=[]

        for i in artist:
            if i=='Unknown':
                continue
            if ';' in i:
                for _ in i.split(';'):
                    artist_set.append(_)
            elif '|' in i:
                for _ in i.split('|'):
                    artist_set.append(_)
            else:
                for _ in i.split(','):
                    artist_set.append(_)
        artist=list(artist_set)
        
        search=[statistics.mode(artist)+' song',choice(artist)+' song',statistics.mode(artist)+' playlist',choice(artist)+' playlist','random song','random songs playlist']
        to_run = partial(ytdl.extract_info, url=choice(search), download=False)
        data = await loop.run_in_executor(None, to_run)
        shelf.close()
        
        for i in data['entries']:
            return i['title']
        
    @classmethod
    async def regather_stream(cls, data, *, loop):
        print("regather")
        """Used for preparing a stream, instead of downloading.
        Since Youtube Streaming links expire."""
        loop = loop or asyncio.get_event_loop()
        requester = data['requester']

        to_run = partial(ytdl.extract_info, url=data['webpage_url'], download=False)
        data = await loop.run_in_executor(None, to_run)
        if 'artist' in data.keys():
            pass
        else:
            data['artist']='Unknown'
        return cls(discord.FFmpegPCMAudio(data['url']), data=data, requester=requester,duration=data['duration'],artist=data['artist'],thumbnail=data['thumbnail'])


class MusicPlayer:

    __slots__ = ('bot', '_guild', '_channel', '_cog', 'queue', 'next', 'current', 'np', 'volume')

    def __init__(self, ctx):
        print("music player init")
        self.bot = ctx.bot
        self._guild = ctx.guild
        self._channel = ctx.channel
        self._cog = ctx.cog

        self.queue = asyncio.Queue()
        self.next = asyncio.Event()

        self.np = None
        self.volume = .5
        self.current = None

        ctx.bot.loop.create_task(self.player_loop())

    async def player_loop(self):
        print('player loop')
        """Our main player loop."""
        await self.bot.wait_until_ready()

        while not self.bot.is_closed():
            self.next.clear()

            try:
                
                async with timeout(30):
                    source = await self.queue.get()
            except asyncio.TimeoutError:
                await self._channel.send("Disconnect from Channel due to Inactivity!")
                return await self.destroy(self._guild)

            if not isinstance(source, YTDLSource):
                try:
                    source = await YTDLSource.regather_stream(source, loop=self.bot.loop)
                except Exception as e:
                    await self._channel.send(f'There was an error processing your song.\n'
                                             f'```css\n[{e}]\n```')
                    continue
            log.add(source)
            print(log)
            Music.write_log(source)
            source.volume = self.volume
            self.current = source
            try:
                self._guild.voice_client.play(source, after=lambda _: self.bot.loop.call_soon_threadsafe(self.next.set))
            except AttributeError:
                return
                
            embeds=discord.Embed(title="Now Playing",description=source.title,color=discord.Color.red())
            embeds.add_field(name='Requested by',value=source.requester.mention,inline=True)
            embeds.add_field(name='Duration',value=f'{source.duration/60:0>2.0f}:{source.duration%60:0>2.0f}',inline=True)
            embeds.add_field(name='Artist',value=source.artist,inline=True)
            embeds.set_thumbnail(url=source.thumbnail)
            embeds.set_footer(text=f"{strftime('%H:%M:%S',localtime()) }")
            self.np = await self._channel.send(embed=embeds)
            
            await self.bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name="A Music | /help"))
            for i in emoji_list.values():
                await self.np.add_reaction(i)
            await self.next.wait()   
            
            source.cleanup()
            self.current = None

            try:
                
                await self.np.delete()
            except discord.HTTPException:
                pass

    async def destroy(self, guild):
        print("destroy")
        """Disconnect and cleanup the player."""
        await self.bot.change_presence(status=discord.Status.idle)
        return self.bot.loop.create_task(self._cog.cleanup(guild))
    


class Music(commands.Cog):
    """Music related commands."""

    __slots__ = ('bot', 'players')

    def __init__(self, bot):
        print("music init")
        self.bot = bot
        self.players = {}
        self.channel=None

    async def cleanup(self, guild):
        print("cleanup")
        try:
            await guild.voice_client.disconnect()
        except AttributeError:
            pass

        try:
            del self.players[guild.id]
        except KeyError:
            pass

    async def __local_check(self, ctx):
        print("local ")
        """A local check which applies to all commands in this cog."""
        if not ctx.guild:
            raise commands.NoPrivateMessage
        return True

    async def __error(self, ctx, error):
        print("error")
        """A local error handler for all errors arising from commands in this cog."""
        if isinstance(error, commands.NoPrivateMessage):
            try:
                return await ctx.send('This command can not be used in Private Messages.')
            except discord.HTTPException:
                pass
        elif isinstance(error, InvalidVoiceChannel):
            await ctx.send('Error connecting to Voice Channel. '
                           'Please make sure you are in a valid channel or provide me with one')

        print('Ignoring exception in command {}:'.format(ctx.command), file=sys.stderr)
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)

    def get_player(self, ctx):
        print("get player")
        """Retrieve the guild player, or generate one."""
        try:
            player = self.players[ctx.guild.id]
        except KeyError:
            player = MusicPlayer(ctx)
            self.players[ctx.guild.id] = player

        return player

    @commands.command(name='connect', aliases=['join'])
    async def connect_(self, ctx, *, channel: discord.VoiceChannel=None):
        """Connect to voice.
        Parameters
        ------------
        channel: discord.VoiceChannel [Optional]
            The channel to connect to. If a channel is not specified, an attempt to join the voice channel you are in
            will be made.
        This command also handles moving the bot to different channels.
        """
        print("command connect")
        if not channel:
            try:
                channel = ctx.author.voice.channel
            except AttributeError:
                raise InvalidVoiceChannel('No channel to join. Please either specify a valid channel or join one.')

        vc = ctx.voice_client
        self.channel=channel
        if vc:
            if vc.channel.id == channel.id:
                return
            try:
                await vc.move_to(channel)
            except asyncio.TimeoutError:
                raise VoiceConnectionError(f'Moving to channel: <{channel}> timed out.')
        else:
            try:
                await channel.connect()
            except asyncio.TimeoutError:
                raise VoiceConnectionError(f'Connecting to channel: <{channel}> timed out.')

        await ctx.send(f'Connected to: **{channel}**', delete_after=2)

    @commands.command(name='play', aliases=['sing','p','s'])
    async def play_(self, ctx, *, search: str):
        """Request a song and add it to the queue.
        This command attempts to join a valid voice channel if the bot is not already in one.
        Uses YTDL to automatically search and retrieve a song.
        Parameters
        ------------
        search: str [Required]
            The song to search and retrieve using YTDL. This could be a simple search, an ID or URL.
        """
        print("command play")
        await ctx.trigger_typing()
        
        
        vc = ctx.voice_client
        
        if not vc:
            await ctx.invoke(self.connect_)
        
        if ctx.author.voice.channel and ctx.author.voice.channel == self.channel:
            pass
        else:
            await ctx.send(embed=discord.Embed(title="You have to be in the Same Channel to Access the Bot",color=discord.Color.red()),delete_after=10)
            return
        

        player = self.get_player(ctx)
        if('playlist?list' in search):
            print('playlsit')
            await ctx.send(embed=discord.Embed(title="Please wait till we process the Playlist for you!",color=discord.Color.red()),delete_after=30)
            source = await YTDLSource.create_source_playlist(ctx, search, loop=self.bot.loop, download=False)
            for i in source:
                await ctx.invoke(self.bot.get_command('play'), search=i)
            return
        elif('open.spotify.com' in search):
            if('track' in search):
                print('spotify track')
                await ctx.send(embed=discord.Embed(title="Please wait till we process the Spotify Song for you!",color=discord.Color.red()),delete_after=2)
                track=sp.track(search.split('/')[-1].split('?')[0])
                search=f"{track['name']} {track['album']['artists'][0]['name']}"
                source = await YTDLSource.create_source(ctx, search, loop=self.bot.loop, download=False)
            else:
                print('spotify playlist')
                await ctx.send(embed=discord.Embed(title="Please wait till we process the Spotify Playlist for you!",color=discord.Color.red()),delete_after=2)
                playlist=sp.user_playlist('spotify',search.split('/')[-1].split('?')[0])
                for items in playlist['tracks']['items']:
                    i=f"{items['track']['name']} {items['track']['album']['artists'][0]['name']}"
                    print(i)
                    await ctx.invoke(self.bot.get_command('play'), search=i)
                return
        else:
            print('track')
            source = await YTDLSource.create_source(ctx, search, loop=self.bot.loop, download=False)
        await player.queue.put(source)

    @commands.command(name='force_play', aliases=['force_sing','fp','fs'])
    async def force_play_(self, ctx, *, search: str):
        print("command force play")
        """Forcely request a song and add it to the queue."""
        await ctx.trigger_typing()
        
        vc = ctx.voice_client

        await self.cleanup(ctx.guild)
        await ctx.invoke(self.bot.get_command('play'), search=search)

    @commands.command(name='pause')
    async def pause_(self, ctx):
        """Pause the currently playing song."""
        print("command pause")
        vc = ctx.voice_client

        if not vc or not vc.is_playing():
            return await ctx.send('I am not currently playing anything!', delete_after=2)
        elif vc.is_paused():
            return

        vc.pause()
        await ctx.send(f'**`{ctx.author}`**: Paused the song!')

    @commands.command(name='resume')
    async def resume_(self, ctx):
        print("command resume")
        """Resume the currently paused song."""
        vc = ctx.voice_client

        if not vc or not vc.is_connected():
            return await ctx.send('I am not currently playing anything!', delete_after=2)
        elif not vc.is_paused():
            return

        vc.resume()
        await ctx.send(f'**`{ctx.author}`**: Resumed the song!')

    @commands.command(name='skip')
    async def skip_(self, ctx):
        print("command skip")

        """Skip the song."""
        vc = ctx.voice_client

        if not vc or not vc.is_connected():
            return await ctx.send('I am not currently playing anything!', delete_after=2)

        if vc.is_paused():
            pass
        elif not vc.is_playing():
            return

        vc.stop()
        await ctx.send(f'**`{ctx.author}`**: Skipped the song!')

    @commands.command(name='queue', aliases=['q', 'playlist'])
    async def queue_info(self, ctx):
        """Retrieve a basic queue of upcoming songs."""
        print("command queue_info")
        vc = ctx.voice_client

        if not vc or not vc.is_connected():
            return await ctx.send('I am not currently connected to voice!', delete_after=2)

        player = self.get_player(ctx)
        if player.queue.empty():
            return await ctx.send('There are currently no more queued songs.')

        
        upcoming = list(itertools.islice(player.queue._queue, 0, 5))

        fmt = '\n'.join(f'**`{_["title"]}`**' for _ in upcoming)
        embed = discord.Embed(title=f'Upcoming - Next {len(upcoming)}', description=fmt,color=discord.Color.red())

        await ctx.send(embed=embed)

    @commands.command(name='now_playing', aliases=['np', 'current', 'currentsong', 'playing'])
    async def now_playing_(self, ctx):
        """Display information about the currently playing song."""
        print("command now playing")
        vc = ctx.voice_client

        if not vc or not vc.is_connected():
            return await ctx.send('I am not currently connected to voice!', delete_after=2)

        player = self.get_player(ctx)
        if not player.current:
            return await ctx.send('I am not currently playing anything!')

        try:
           
            await player.np.delete()
        except discord.HTTPException:
            pass

        
        embeds=discord.Embed(title="Now Playing",description=vc.source.title,color=discord.Color.red())
        embeds.add_field(name='Requested by',value=vc.source.requester.mention,inline=True)
        embeds.add_field(name='Duration',value=f'{vc.source.duration/60:0>2.0f}:{vc.source.duration%60:0>2.0f}',inline=True)
        embeds.add_field(name='Artist',value=vc.source.artist,inline=True)
        embeds.set_thumbnail(url=vc.source.thumbnail)
        embeds.set_footer(text=f"{strftime('%H:%M:%S',localtime()) }")
        self.np = await ctx.send(embed=embeds)
        log.add(vc.source)
        self.write_log(vc.source)    
        for i in emoji_list.values():
            await self.np.add_reaction(i)

    @commands.command(name='volume', aliases=['vol'])
    async def change_volume(self, ctx, *, vol: float):
        """Change the player volume.
        Parameters
        ------------
        volume: float or int [Required]
            The volume to set the player to in percentage. This must be between 1 and 100.
        """
        print("command change volume")
        vc = ctx.voice_client

        if not vc or not vc.is_connected():
            return await ctx.send('I am not currently connected to voice!', delete_after=2)

        if not 0 < vol < 101:
            return await ctx.send('Please enter a value between 1 and 100.')

        player = self.get_player(ctx)

        if vc.source:
            vc.source.volume = vol / 100

        player.volume = vol / 100
        await ctx.send(f'**`{ctx.author}`**: Set the volume to **{vol}%**')

    @commands.command(name='stop')
    async def stop_(self, ctx):
        """Stop the currently playing song and destroy the player.
        !Warning!
            This will destroy the player assigned to your guild, also deleting any queued songs and settings.
        """
        print("command stop")
        vc = ctx.voice_client

        if not vc or not vc.is_connected():
            return await ctx.send('I am not currently playing anything!', delete_after=2)

        await self.cleanup(ctx.guild)
    @commands.Cog.listener()
    async def on_reaction_add(self,reaction,user):
        voice = self.bot.voice_clients
        print("listener")
        if(user.name==str(self.bot.user)[:-5]):
            pass
        else:
            
            if(reaction.emoji==emoji_list['playpause']):  
                if voice[0].is_playing():
                    voice[0].pause()
                    await reaction.message.channel.send("The audio is paused.",delete_after=2)
                else:
                    voice[0].resume()
                    await reaction.message.channel.send("The audio is resumed.",delete_after=2)
                await reaction.message.remove_reaction(reaction.emoji,user)
            
            elif(reaction.emoji==emoji_list['stop']):
                
                if voice[0].is_playing():
                    await self.cleanup(voice[0].guild)
                    await reaction.message.channel.send("The audio is Stop.",delete_after=2)
                else:
                    await reaction.message.channel.send("Currently no audio is playing.",delete_after=2)
                return
            

            elif(reaction.emoji==emoji_list['skip']):
                vc=voice[0]
                if not vc or not vc.is_connected():
                    return await reaction.message.channel.send('I am not currently playing anything!', delete_after=2)

                if vc.is_paused():
                    pass
                elif not vc.is_playing():
                    return

                vc.stop()
                await reaction.message.channel.send(f'**`{user.name}`**: Skipped the song!', delete_after=2)

            elif(reaction.emoji==emoji_list['plus']):
                vc = voice[0]

                if not vc or not vc.is_connected():
                    return await reaction.message.channel.send('I am not currently connected to voice!', delete_after=2)

                player = self.get_player(reaction.message.channel)

                if vc.source:
                    vc.source.volume = vc.source.volume + 10 / 100

                player.volume = vc.source.volume
                await reaction.message.channel.send(f'**`{user.name}`**: Increased the volume by **{10}%**', delete_after=2)
                await reaction.message.remove_reaction(reaction.emoji,user)
            
            elif(reaction.emoji==emoji_list['minus']):
                vc = voice[0]

                if not vc or not vc.is_connected():
                    return await reaction.message.channel.send('I am not currently connected to voice!', delete_after=2)

                player = self.get_player(reaction.message.channel)

                if vc.source:
                    vc.source.volume = vc.source.volume - 10 / 100

                player.volume = vc.source.volume
                await reaction.message.channel.send(f'**`{user.name}`**: decreased the volume by **{10}%**', delete_after=2)
                await reaction.message.remove_reaction(reaction.emoji,user)
    
    @commands.command(name='current_log',aliases=['cl','ch','current_history'])
    async def curr_log_(self,ctx):
        """This commands returns the current logs/History"""
        print("command current log")
        fmt = '\n'.join(f'**`{_.title}`**' for _ in log)
        embed = discord.Embed(title=f'History {len(log)}', description=fmt,color=discord.Color.red())
        await ctx.send(embed=embed)
    
    # @commands.command(name='log',aliases=['history'])
    # async def log_(self,ctx):
    #     """This commands returns the all logs/History"""
    #     print("command log")
    #     shelf=shelve.open('F:\OneDrive\Documents\Python-MProject\Main\data\music_log',flag='r')
    #     # fmt = '\n'.join(f'**`{_[0]}: {_[1]["name"]}`**' for _ in shelf.items())
    #     for i in shelf.items():
    #         await ctx.send(f"{i[0]}: {i[1]['name']}")
    #     # embed = discord.Embed(title=f'History {len(shelf)}', description=fmt,color=discord.Color.red())
    #     # await ctx.send(fmt)
    #     shelf.close()
    
    @classmethod
    def write_log(self,source):
        print("write log")
        shelf=shelve.open('F:\OneDrive\Documents\Python-MProject\Main\data\music_log')
        dict={'name':source.title,'artist':source.artist,'duration':source.duration,'url':source.web_url,'user':source.requester.id}
        
        shelf[strftime('%m/%d/%Y,%H:%M:%S',localtime())]=dict
        shelf.close()
    
    @commands.command(name='suggest')
    async def create_suggestion(self,ctx):
        """This command suggests you a song according to data"""
        print("command suggest")
        title=await YTDLSource.create_suggestion(self.bot.loop)
        await ctx.send(f"Suggested Song: {title}\nSend 0 to Cancel within 5 Sec",delete_after=6)
        def check(msg):
            return msg.author == ctx.author and msg.channel == ctx.channel and \
            msg.content.lower() in ['0']
        try:
            msg = await self.bot.wait_for("message", check=check,timeout=5)
            if msg.content.lower() == '0':
                await ctx.send("You Have cancelled the Suggesstion",delete_after=2)
        except asyncio.TimeoutError:
            await ctx.invoke(self.bot.get_command('play'), search=title)
          
def setup(bot):
    print("Set up youtube")
    bot.add_cog(Music(bot))