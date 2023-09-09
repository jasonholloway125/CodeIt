import datetime as dt
import discord as disc
from discord.ext import tasks
import openai
import sys
import os
import json



class CodeIt(disc.Client):
    """
    CodeIt class is responsible for running the CodeIt Discord application. 
    Use CodeIt.run('token key') to run the bot.
    """
    def __init__(self, intents: disc.Intents, openai_key: str) -> None:
        super().__init__(intents=intents)
        openai.api_key = openai_key

        self.__initial_prompt = """
        You are a Discord bot that will provide small programming challenges for programmers. These challenges should ask users to create a program. 

        You will receive a request in the form of a JSON string that will look like: {"language": "LANGUAGE_VALUE", "difficulty": "DIFFICULTY_VALUE"}
        However, LANGUAGE_VALUE will be the programming language the challenge will be based on (e.g., 'python', 'java', 'c', 'c++', etc.).
        The DIFFICULTY_VALUE will be the level of difficulty for the programming challenge. This can be a number between 1 and 3, where 3 is the highest difficulty and 1 is the lowest.
        
        Your response will be a JSON string that will look like: {"challenge": "CHALLENGE_VALUE", "clue": "CLUE_VALUE", "solution": "SOLUTION_VALUE"}
        However, CHALLENGE_VALUE will be the explanation of the program that needs to be made that will be shared with users.
        The CLUE_VALUE is the clue that will be shared with users to help them create the program.
        SOLUTION_VALUE is a model solution to show users what a good solution looks like.
        IT IS VERY IMPORTANT THAT YOU KEEP TO THE STATED FORMAT OF THE JSON STRING RESPONSE. THE DISCORD BOT CANNOT WORK OTHERWISE.
        ALSO NOTE THAT THE RESPONSE NEEDS TO BE FORMATTED SO THAT the json.loads() function in Python can convert your response into a dictionary. 

        These challenges should not ask users to create a very large program with thousands of lines of code.
        The challenges should be more or less relevant to the common uses of the chosen programming language.
        The challenges should be unique. 

        If you cannot provide a challenge, simply respond with: NULL
        """

        self.__languages = ['python', 'c#', 'c++', 'javascript', 'php', 'swift', 'java', 'go', 'sql', 'ruby', 'c']
        self.__difficulties = ['1', '2', '3']

        self.__conversations = {}
        self.__cca = {}

    async def send_msg(self, channel: disc.TextChannel, message: str):
        """
        Sends a message to the specified text channel.
        """
        
        await channel.send(message)


    async def on_guild_join(self, guild: disc.Guild):
        """
        Sends a 'welcome message' upon being added to a Discord server.
        """
        old_channel = self.__get_oldest_channel__(guild)

        await self.send_msg(old_channel, "Thank you for adding CodeIt! I may not be pretty, but I am useful! For a full list of commands, please enter **!ci help**.")


    async def on_ready(self):
        """
        Executes when the Discord bot is enabled. Will begin the 24-hour cycle of clearing old conversations.
        """
        await self.__clear_conversation__.start()    


    async def on_message(self, message: str):
        """
        Executes when a text channel the Discord bot can view receives a new message. 
        It's responsible for responding to !ci messages.
        """

        if message.author == self.user:
            return
        
        msg: list = message.content.strip().lower().split()
        if msg[0] == '!ci':

            if len(msg) == 1:
                await self.send_msg(message.channel, 'Please use **!ci help** to see the list of available commands.')
                return

            match msg[1]:
                case 'help':
                    await self.send_msg(message.channel, '## CODEIT COMMANDS\n'
                                        '**!ci languages**: get a list of supported languages.\n'
                                        '**!ci next *language[supported language]* *difficulty[no. between 1-3]***: request a new challenge. \n'
                                        '**!ci repeat**: display the last challenge.\n'
                                        '**!ci clue**: display the clue.\n'
                                        '**!ci solution**: display the example solution.\n'
                                        '**!ci help**: display the list of available commands.')
                    
                case 'next':

                    if len(msg) <= 2 or msg[2] not in self.__languages or msg[3] not in self.__difficulties:

                        await self.send_msg(message.channel, 'Please insert a valid language or difficulty. Find the supported languages using **!ci languages**. Difficulties range from 1 to 3.')
                    else:
                        request = {
                            "language": msg[2],
                            "difficulty": msg[3]
                        }
                        response = self.__get_chatgpt_response__(str(request), message.guild.id)


                        if self.__filter_qa_response__(response, request, message.guild.id):

                            await self.send_msg(message.channel, self.__cca[message.guild.id]['challenge'])
                        else:

                            await self.send_msg(message.channel, 'A challenge failed to load. Please repeat the command or change the parameters.')
                        

                case 'repeat':
                    
                    if(self.__cca.get(message.guild.id) is None):
                        await self.send_msg(message.channel, 'There is no loaded challenge. Please use **!ci next *language[supported language]* *difficulty[no. between 1-3]*** to load a new question.')

                    else:
                        await self.send_msg(message.channel, self.__cca[message.guild.id]['challenge'])

                case 'clue':

                    if(self.__cca.get(message.guild.id) is None):
                        await self.send_msg(message.channel, 'There is no loaded clue. Please use **!ci next *language[supported language]* *difficulty[no. between 1-3]*** to load a new question.')

                    else:
                        await self.send_msg(message.channel, self.__cca[message.guild.id]['clue'])

                case 'solution':

                    if(self.__cca.get(message.guild.id) is None):
                        await self.send_msg(message.channel, 'There is no loaded solution. Please use **!ci next *language[supported language]* *difficulty[no. between 1-3]*** to load a new question.')

                    else:
                        await self.send_msg(message.channel, self.__cca[message.guild.id]['solution'])


                case 'languages':

                    languages = ', '.join(self.__languages)
                    languages = '## Supported Languages\n' + languages

                    await self.send_msg(message.channel, languages)
                case _:

                    await self.send_msg(message.channel, 'Please use **!ci help** to see the list of available commands.')


    def __get_oldest_channel__(self, guild: disc.Guild) -> disc.TextChannel:
        """
        Returns the oldest text channel the Discord bot can view from a specified Discord server.
        """
        old_cha = None
        for channel in guild.text_channels:
            if old_cha is None or channel.created_at < old_cha.created_at:
                old_cha = channel
        return old_cha


    def __add_conversation__(self, guild_id: int):
        """
        Adds a new item to self.__conversations. 
        self.__conversations is used to distinguish between ChatGPT correspondance between different servers.
        """

        self.__conversations[guild_id] = {
            "last_updated": dt.datetime.now(),
            "messages": [{"role": "system", "content": self.__initial_prompt}]}
        

    @tasks.loop(hours=24)
    async def __clear_conversation__(self):
        """
        Every 24 hours, a conversation that has not been updated in 86340 seconds (~24 hours) will be removed. 
        It is used to free up memory.
        """
        now = dt.datetime.now()
        for key, value in self.__conversations.items():
            dif: dt.timedelta = now - value['last_updated']
            if dif.seconds > 86340:
                self.__remove_conversation__(key)


    def __remove_conversation__(self, guild_id: int):
        """
        Deletes records for a specified server.
        """

        del self.__conversations[guild_id]
        del self.__cca[guild_id]


    def __filter_qa_response__(self, response: str, request: dict, guild_id: int) -> bool:
        """
        Processes the ChatGPT response for a new challenge, clue, and solution.
        Returns true if the values are not empty. 
        """

        try:
            cca = json.loads(response)
            
            language = request['language'].upper()
            cca['challenge'] = '## {0} CHALLENGE\n\n'.format(language) + cca['challenge']
            cca['clue'] = '## {0} CHALLENGE CLUE\n\n'.format(language) + cca['clue']
            cca['solution'] = '## {0} CHALLENGE SOLUTION\n\n'.format(language) + cca['solution']

            self.__cca[guild_id] = cca
            return True
        except:
            return False


    def __update_conversation_time__(self, guild_id: int):
        """
        Updates the time for when the conversation was last changed.
        """
        if self.__conversations.get(guild_id) is None:
            return
        self.__conversations[guild_id]['last_updated'] = dt.datetime.now()


    def __get_chatgpt_response__(self, msg: str, guild_id: int) -> str:
        """
        Sends prompt to ChatGPT and receives response. 
        Appends messages to message history in self.__conversations.
        """
        if self.__conversations.get(guild_id) is None: 
            self.__add_conversation__(guild_id)
        self.__conversations[guild_id]['messages'].append({"role": "user", "content": msg})
        response = openai.ChatCompletion.create(
            model = "gpt-3.5-turbo-0301",
            messages = self.__conversations[guild_id]['messages']
        )


        refined = response["choices"][0]["message"]["content"]
        self.__conversations[guild_id]['messages'].append({"role": "assistant", "content": refined})
        self.__update_conversation_time__(guild_id)
        return refined


# Code to run CodeIt
if __name__ == '__main__':
    openai_key = 'OPENAI KEY HERE'
    discord_token = 'DISCORD TOKEN HERE'

    intents = disc.Intents.default()
    intents.message_content = True

    client = CodeIt(intents=intents, openai_key=openai_key)
    client.run(discord_token)

