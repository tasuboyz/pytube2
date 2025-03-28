# -*- coding: utf-8 -*-
"""Module for interacting with a user's youtube channel."""
import json
import logging
from typing import Dict, List, Optional, Tuple, Iterable

from pytube import extract, YouTube, Playlist, request
from pytube.helpers import uniqueify, DeferredGeneratorList

logger = logging.getLogger(__name__)


class Channel(Playlist):
    def __init__(self, url: str, proxies: Optional[Dict[str, str]] = None):
        """Construct a :class:`Channel <Channel>`.

        :param str url:
            A valid YouTube channel URL.
        :param proxies:
            (Optional) A dictionary of proxies to use for web requests.
        """
        super().__init__(url, proxies)

        self.channel_uri = extract.channel_name(url)

        self.channel_url = f"https://www.youtube.com{self.channel_uri}"

        self.videos_url = self.channel_url + "/videos"
        self.shorts_url = self.channel_url + "/shorts"
        self.playlists_url = self.channel_url + "/playlists"
        self.community_url = self.channel_url + "/community"
        self.featured_channels_url = self.channel_url + "/channels"
        self.about_url = self.channel_url + "/about"

        # Possible future additions
        self._playlists_html = None
        self._community_html = None
        self._featured_channels_html = None
        self._about_html = None
        self._html_page = self.videos_url  # Videos will be preferred over short videos
        self._visitor_data = None

    @property
    def channel_name(self):
        """Get the name of the YouTube channel.

        :rtype: str
        """
        return self.initial_data["metadata"]["channelMetadataRenderer"]["title"]

    @property
    def channel_id(self):
        """Get the ID of the YouTube channel.

        This will return the underlying ID, not the vanity URL.

        :rtype: str
        """
        return self.initial_data["metadata"]["channelMetadataRenderer"]["externalId"]

    @property
    def vanity_url(self):
        """Get the vanity URL of the YouTube channel.

        Returns None if it doesn't exist.

        :rtype: str
        """
        return self.initial_data["metadata"]["channelMetadataRenderer"].get(
            "vanityChannelUrl", None
        )  # noqa:E501

    @property
    def html(self):
        """Get the html for the /videos page.

        :rtype: str
        """
        if self._html:
            return self._html
        self._html = request.get(self._html_page)
        return self._html

    @property
    def playlists_html(self):
        """Get the html for the /playlists page.

        Currently unused for any functionality.

        :rtype: str
        """
        if self._playlists_html:
            return self._playlists_html
        else:
            self._playlists_html = request.get(self.playlists_url)
            return self._playlists_html

    @property
    def community_html(self):
        """Get the html for the /community page.

        Currently unused for any functionality.

        :rtype: str
        """
        if self._community_html:
            return self._community_html
        else:
            self._community_html = request.get(self.community_url)
            return self._community_html

    @property
    def featured_channels_html(self):
        """Get the html for the /channels page.

        Currently unused for any functionality.

        :rtype: str
        """
        if self._featured_channels_html:
            return self._featured_channels_html
        else:
            self._featured_channels_html = request.get(self.featured_channels_url)
            return self._featured_channels_html

    @property
    def about_html(self):
        """Get the html for the /about page.

        Currently unused for any functionality.

        :rtype: str
        """
        if self._about_html:
            return self._about_html
        else:
            self._about_html = request.get(self.about_url)
            return self._about_html

    def _build_continuation_url(self, continuation: str) -> Tuple[str, dict, dict]:
        """Helper method to build the url and headers required to request
        the next page of videos
        :param str continuation: Continuation extracted from the json response
            of the last page
        :rtype: Tuple[str, dict, dict]
        :returns: Tuple of an url and required headers for the next http
            request
        """
        return (
            (
                # was changed to this format (and post requests)
                # between 2022.11.06 and 2022.11.20
                "https://www.youtube.com/youtubei/v1/browse?key="
                f"{self.yt_api_key}"
            ),
            {
                "X-YouTube-Client-Name": "1",
                "X-YouTube-Client-Version": "2.20200720.00.02",
            },
            # extra data required for post request
            {
                "continuation": continuation,
                "context": {
                    "client": {
                        "clientName": "WEB",
                        "visitorData": self._visitor_data,
                        "clientVersion": "2.20200720.00.02",
                    }
                },
            },
        )

    # @staticmethod
    # def _extract_videos(raw_json: str) -> Tuple[List[str], Optional[str]]:
    def _extract_videos(self, raw_json: str) -> Tuple[List[str], Optional[str]]:
        """Extracts videos from a raw json page

        :param str raw_json: Input json extracted from the page or the last
            server response
        :rtype: Tuple[List[str], Optional[str]]
        :returns: Tuple containing a list of up to 100 video watch ids and
            a continuation token, if more videos are available
        """
        initial_data = json.loads(raw_json)
        # this is the json tree structure, if the json was extracted from
        # html
        try:
            try:
                # This is the json tree structure for videos
                videos = initial_data["contents"]["twoColumnBrowseResultsRenderer"][
                    "tabs"
                ][1]["tabRenderer"]["content"]["richGridRenderer"]["contents"]

            except (KeyError, IndexError, TypeError):
                # This is the json tree structure for short videos
                videos = initial_data["contents"]["twoColumnBrowseResultsRenderer"][
                    "tabs"
                ][2]["tabRenderer"]["content"]["richGridRenderer"]["contents"]

            # This is the json tree structure of visitor data
            # It is necessary to send the visitorData together with the continuation token
            self._visitor_data = initial_data["responseContext"][
                "webResponseContextExtensionData"
            ]["ytConfigData"]["visitorData"]
        except (KeyError, IndexError, TypeError):
            try:
                # this is the json tree structure, if the json was directly sent
                # by the server in a continuation response
                important_content = initial_data[1]["response"][
                    "onResponseReceivedActions"
                ][0]["appendContinuationItemsAction"]["continuationItems"]
                videos = important_content
            except (KeyError, IndexError, TypeError):
                try:
                    # this is the json tree structure, if the json was directly sent
                    # by the server in a continuation response
                    # no longer a list and no longer has the "response" key
                    important_content = initial_data["onResponseReceivedActions"][0][
                        "appendContinuationItemsAction"
                    ]["continuationItems"]
                    videos = important_content
                except (KeyError, IndexError, TypeError) as p:
                    logger.info(p)
                    return [], None

        try:
            continuation = videos[-1]["continuationItemRenderer"][
                "continuationEndpoint"
            ]["continuationCommand"]["token"]
            videos = videos[:-1]
        except (KeyError, IndexError):
            # if there is an error, no continuation is available
            continuation = None

        # only extract the video ids from the video data
        videos_url = []
        try:
            # Extract id from videos
            for x in videos:
                videos_url.append(
                    f"/watch?v="
                    f"{x['richItemRenderer']['content']['videoRenderer']['videoId']}"
                )
        except (KeyError, IndexError, TypeError):
            # Extract id from short videos
            for x in videos:
                # videos_url.append(f"/watch?v="
                #                   f"{x['richItemRenderer']['content']['reelItemRenderer']['videoId']}")
                videos_url.append(
                    f"/watch?v="
                    f"{x['richItemRenderer']['content']['shortsLockupViewModel']['entityId'][-11:]}"
                )
        return uniqueify(videos_url), continuation

    @property
    def videos(self) -> Iterable[YouTube]:
        """Yields YouTube objects of videos in this channel
        :rtype: List[YouTube]
        :returns: List of YouTube
        """
        self._html_page = self.videos_url  # Set video tab
        return DeferredGeneratorList(self.videos_generator())

    @property
    def shorts(self) -> Iterable[YouTube]:
        """Yields YouTube objects of short videos in this channel
        :rtype: List[YouTube]
        :returns: List of YouTube
        """
        self._html_page = self.shorts_url  # Set shorts tab
        return DeferredGeneratorList(self.videos_generator())
