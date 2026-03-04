from mail_helper.config import load_config
from mail_helper.tui.app import MailHelperApp


def main() -> None:
    config = load_config()
    app = MailHelperApp(config)
    app.run()


if __name__ == "__main__":
    main()
