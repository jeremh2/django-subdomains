import logging
import re
import warnings

from django.conf import settings
from django.contrib.sites.models import Site
from django.utils.cache import patch_vary_headers

from subdomains.exceptions import IncorrectSiteException


logger = logging.getLogger(__name__)


class SubdomainMiddleware(object):
    def get_domain(self):
        return Site.objects.get_current().domain

    def process_request(self, request):
        """
        Adds a `subdomain` attribute to the request object, which corresponds
        to the portion of the URL before the current Site object's `domain`
        attribute.
        """
        domain = self.get_domain()

        # To allow for case-insensitive comparison, force the site.domain and
        # the HTTP Host to lowercase.
        domain, host = domain.lower(), request.get_host().lower()

        REMOVE_WWW_FROM_DOMAIN = getattr(settings, 'REMOVE_WWW_FROM_DOMAIN',
            False)
        if REMOVE_WWW_FROM_DOMAIN and domain.startswith("www."):
            domain = domain.replace("www.", "", 1)

        pattern = r'^(?:(?P<subdomain>.*?)\.)?%s(?::.*)?$' % re.escape(domain)
        matches = re.match(pattern, host)

        request.subdomain = None

        if matches:
            request.subdomain = matches.group('subdomain')
        else:
            error = 'The current host %s does not belong to the current ' \
                'domain.' % request.get_host()

            if getattr(settings, 'USE_SUBDOMAIN_EXCEPTION', False):
                raise IncorrectSiteException(error)
            else:
                warnings.warn('%s The URLconf for this host will fall back to '
                    'the ROOT_URLCONF.' % error, UserWarning)

        # Continue processing the request as normal.
        return None


class SubdomainURLRoutingMiddleware(SubdomainMiddleware):
    def process_request(self, request):
        """
        Sets the current request's `urlconf` attribute to the URL conf
        associated with the subdomain, if listed in `SUBDOMAIN_URLCONFS`.
        """
        super(SubdomainURLRoutingMiddleware, self).process_request(request)

        subdomain = getattr(request, 'subdomain', False)

        if subdomain is not False:
            urlconf = settings.SUBDOMAIN_URLCONFS.get(subdomain)
            if urlconf is not None:
                logger.debug("Using urlconf '%s' for subdomain: %s",
                    urlconf, repr(subdomain))
                request.urlconf = urlconf

        # Continue processing the request as normal.
        return None

    def process_response(self, request, response):
        """
        Forces the HTTP Vary header onto requests to avoid having responses
        cached from incorrect urlconfs.

        If you'd like to disable this for some reason, set `FORCE_VARY_ON_HOST`
        in your Django settings file to `False`.
        """
        if getattr(settings, 'FORCE_VARY_ON_HOST', True):
            patch_vary_headers(response, ('Host',))

        return response
