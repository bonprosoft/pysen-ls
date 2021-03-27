import argparse
import logging

from .server import ConnectionMethod, Server

_logger = logging.getLogger(__name__)


def setup_logger() -> None:
    handler = logging.FileHandler("pysen_ls.log", mode="w")
    handler.setLevel(logging.INFO)

    package_logger = logging.getLogger("pysen_ls")
    package_logger.addHandler(handler)
    package_logger.setLevel(logging.INFO)

    # NOTE: To suppress warnings like `Ignoring notification for unknown method`
    pygls_logger = logging.getLogger("pygls")
    pygls_logger.setLevel(logging.ERROR)


def main() -> None:
    setup_logger()
    parser = argparse.ArgumentParser("pysen-ls")
    method_options = parser.add_mutually_exclusive_group(required=True)
    method_options.add_argument(
        "--tcp",
        action="store_const",
        dest="method",
        const=ConnectionMethod.TCP,
        help="Use tcp to communicate with a client.",
    )
    method_options.add_argument(
        "--io",
        action="store_const",
        dest="method",
        const=ConnectionMethod.IO,
        help="Use stdio to communicate with a client.",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Hostname for the tcp server. Only works with --tcp.",
    )
    parser.add_argument(
        "--port",
        default=3746,
        help="Port number for the tcp server. Only works with --tcp.",
    )
    args = parser.parse_args()

    server = Server(args.method, args.host, args.port)
    server.start()


if __name__ == "__main__":
    main()
