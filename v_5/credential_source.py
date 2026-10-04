"""Boundary for an authorized ARRT credential feed.

Nothing behind this interface exists yet, and that is deliberate. ARRT offers
no public API, and their online directory is protected by an anti-robot check.
Driving that check with a script, a headless browser, or an AI agent would be
circumventing an access control, and verification evidence obtained that way
would not stand up in a survey.

So the rest of the tool never calls ARRT. It calls fetch_credential(), which
currently refuses, and every verified date comes from a human lookup recorded
through record_verification.py.

If Beacon later obtains an authorized feed -- a direct arrangement with ARRT,
or a primary source verification vendor that already has one -- implement
fetch_credential() here. Nothing else in the pipeline needs to change.

ARRT employer inquiries: 651-687-0048
"""


class CredentialSourceUnavailable(RuntimeError):
    """Raised when no authorized automated source is configured."""


def is_configured():
    """True once an authorized feed is implemented."""
    return False


def fetch_credential(last_name, first_name, arrt_id=None):
    """Return credential status for one person from an authorized source.

    An implementation should return a dict shaped like:

        {
            "credentials": "R.T.(R)(CT)(ARRT)",
            "valid_thru": "10/2027",      # MM/YYYY
            "source": "ARRT employer feed",
        }

    Until then this raises, and the human workflow stays the only path.
    """
    raise CredentialSourceUnavailable(
        "No authorized ARRT feed is configured. Verification is performed by a "
        "person and recorded with record_verification.py. See the module "
        "docstring for how to enable an automated source."
    )
