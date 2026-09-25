"""Dataset egress policy: exact provider hosts, HTTPS and validated redirects."""

from urllib.parse import urlsplit

ALLOWED_DATA_HOSTS = frozenset(
    {
        "raw.githubusercontent.com",
        "ndownloader.figshare.com",
        "api.figshare.com",
        "s3-eu-west-1.amazonaws.com",
        "s3.amazonaws.com",
    }
)


def validate_data_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme != "https":
        raise ValueError("dataset downloads require HTTPS")
    if parsed.username or parsed.password or parsed.fragment or parsed.port not in {None, 443}:
        raise ValueError("invalid dataset URL authority or fragment")
    if parsed.hostname not in ALLOWED_DATA_HOSTS:
        raise ValueError("dataset download host is not allowlisted")
    # Only the Figshare bucket is allowed on shared S3 endpoints.
    if parsed.hostname in {"s3-eu-west-1.amazonaws.com", "s3.amazonaws.com"}:
        if not parsed.path.startswith("/pfigshare-u-files/"):
            raise ValueError("only the Figshare bucket is allowed on this host")
