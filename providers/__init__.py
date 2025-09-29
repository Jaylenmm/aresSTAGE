import os

from providers.odds_client import OddsClient as OddsApiClient


def get_props_client():
    provider = (os.getenv('ODDS_PROPS_PROVIDER') or 'oddsapi').lower()
    if provider == 'sgo':
        try:
            from providers.sgo_client import SportsGameOddsClient
            return SportsGameOddsClient()
        except Exception:
            return OddsApiClient()
    return OddsApiClient()

"""Provider clients package."""

