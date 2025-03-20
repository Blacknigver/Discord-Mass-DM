import discum


class Scraper:
    """
    Scrapes members from a Discord guild using discum.

    Attributes:
        guild_id (str): The ID of the guild to scrape.
        channel_id (str): The ID of the channel to use for fetching members.
        token (str): The Discord token for authentication.
        scraped (list): A list to store scraped member data.
    """

    def __init__(self, guild_id, channel_id, token):
        """
        Initializes the Scraper with guild ID, channel ID, and token.

        Args:
            guild_id (str): The target guild ID.
            channel_id (str): The target channel ID.
            token (str): The Discord token.
        """
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.token = token
        self.scraped = []

    def scrape(self):
        """
        Fetches members from the specified guild and channel using discum.
        
        This method initializes a discum client, starts member fetching,
        waits until the operation is complete, and then populates the
        'scraped' list with the fetched member data.
        """
        try:
            client = discum.Client(token=self.token, log=False)
            # Begin fetching members from the guild and channel
            client.gateway.fetchMembers(self.guild_id, self.channel_id, reset=False, keep="all")

            @client.gateway.command
            def scraper_command(resp):
                try:
                    if client.gateway.finishedMemberFetching(self.guild_id):
                        # Remove the command and close the gateway once finished
                        client.gateway.removeCommand(scraper_command)
                        client.gateway.close()
                except Exception:
                    pass

            client.gateway.run()

            # Append each member to the scraped list
            for user in client.gateway.session.guild(self.guild_id).members:
                self.scraped.append(user)

            client.gateway.close()
        except Exception:
            return

    def fetch(self):
        """
        Triggers the scraping process and returns the scraped member list.

        Returns:
            list: The list of scraped members. If no members are scraped,
                  the function retries until data is available.
        """
        try:
            self.scrape()
            if not self.scraped:
                return self.fetch()
            return self.scraped
        except Exception:
            self.scrape()
            if not self.scraped:
                return self.fetch()
            return self.scraped
