import re

from youtube_dl.extractor.common import InfoExtractor

from youtube_dl.compat import (
    compat_urllib_parse,
    compat_urllib_parse_urlparse,
)

from youtube_dl.utils import (
    ExtractorError,
    int_or_none,
    url_or_none,
    parse_filesize,
    urlencode_postdata,
    HEADRequest,
    determine_ext,
    mimetype2ext,
)


class Owncloud(InfoExtractor):
    IE_NAME = 'owncloud'
    _INSTANCES_RE = r'''(?:
                            .*\.?sciebo\.de|
                            cloud\.uni-koblenz-landau\.de
                        )'''

    _VALID_URL = (
        r'''(?x)
            (?P<server>https?://%s)/s/
            (?P<id>[A-Za-z0-9\-_.]+)
            (?P<extra>/.*)?
        '''
        % _INSTANCES_RE
    )

    def _real_extract(self, url):

        mobj = re.match(self._VALID_URL, url)
        server = mobj.group('server')
        video_id = mobj.group('id')
        url_extra = mobj.group('extra')

        landing_url = server + '/s/' + video_id
        landing_webpage, urlh = self._download_webpage_handle(url, landing_url, 'Downloading Owncloud landing page')
        opend_landing_url = urlh.geturl()

        password_protected = self._search_regex(
            r'<label[^>]+?for="(password)"', landing_webpage, 'password field', fatal=False, default=None
        )
        if password_protected is not None:
            # Password protected
            landing_webpage, urlh = self._verify_video_password(landing_webpage, opend_landing_url, video_id)

        landing_inputs = self._hidden_inputs(landing_webpage)

        title = landing_inputs.get('filename', 'Unknown title')
        # could be used for mimetype2ext
        # mimetype = landing_inputs.get('mimetype', None)

        filesize = landing_inputs.get('filesize', None)
        download_url = landing_inputs.get('downloadURL', None)

        if download_url is None:
            download_url = self._extend_to_download_url(urlh.geturl())

        ext_req = HEADRequest(download_url)
        ext_handle = self._request_webpage(ext_req, video_id, note='Determining extension')
        ext = self.urlhandle_detect_ext(ext_handle)

        formats = []
        formats.append(
            {
                'url': url_or_none(download_url),
                'ext': ext,
                'filesize': int_or_none(filesize),
            }
        )
        self._sort_formats(formats)

        return {'id': video_id, 'title': title, 'formats': formats}

    def urlhandle_detect_ext(self, url_handle):
        getheader = url_handle.headers.get

        cd = getheader('Content-Disposition')
        if cd:
            m = re.match(r'attachment;.*filename="(?P<filename>[^"]+)"', cd)
            if m:
                e = determine_ext(m.group('filename'), default_ext=None)
                if e:
                    return e

        return mimetype2ext(getheader('Content-Type'))

    def _extend_to_download_url(self, url: str) -> str:
        """
        Adds the string /download to a URL
        @param url: The URL where the string should be added.
        @return: The URL with the string.
        """

        url_parts = list(compat_urllib_parse_urlparse(url))
        url_parts[2] = url_parts[2].rstrip('/') + '/download'
        return compat_urllib_parse.urlunparse(url_parts)

    def _verify_video_password(self, webpage, url, video_id):
        password = self._downloader.params.get('videopassword')
        if password is None:
            raise ExtractorError(
                'This video is protected by a password, use the --video-password option', expected=True
            )
        requesttoken = self._search_regex(r'<input[^>]+?name="requesttoken" value="([^\"]+)"', webpage, 'requesttoken')
        data = urlencode_postdata({'requesttoken': requesttoken, 'password': password})

        validation_response, urlh = self._download_webpage_handle(
            url, video_id, note='Validating Password...', errnote='Wrong password?', data=data
        )

        password_protected = self._search_regex(
            r'<label[^>]+?for="(password)"', validation_response, 'password field', fatal=False, default=None
        )
        warning = self._search_regex(
            r'<div[^>]+?class="warning">([^<]*)</div>',
            validation_response,
            'warning',
            fatal=False,
            default="The password is wrong. Try again.",
        )
        if password_protected is not None:
            raise ExtractorError('Login failed, %s said: %r' % (self.IE_NAME, warning), expected=True)
        return validation_response, urlh
