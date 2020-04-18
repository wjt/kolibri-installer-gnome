import logging
import os
import subprocess
import threading
from gettext import gettext as _

import pew
import pew.ui
from pew.ui import PEWShortcut

from . import config
from .kolibri_redirect import KolibriPoller
from .kolibri_service import KolibriServiceThread
from .utils import KOLIBRI_URL, KOLIBRI_HOME


class MenuEventHandler:
    def on_documentation(self):
        subprocess.call(['xdg-open', 'https://kolibri.readthedocs.io/en/latest/'])

    def on_forums(self):
        subprocess.call(['xdg-open', 'https://community.learningequality.org/'])

    def on_new_window(self):
        app = pew.ui.get_app()
        if app:
            window = app.create_kolibri_window(KOLIBRI_URL)
            app.windows.append(window)
            window.show()

    def on_close_window(self):
        self.close()

    def on_open_in_browser(self):
        subprocess.call(['xdg-open', self.get_url()])

    def on_open_kolibri_home(self):
        subprocess.call(['xdg-open', KOLIBRI_HOME])

    def on_back(self):
        self.go_back()

    def on_forward(self):
        self.go_forward()

    def on_reload(self):
        self.reload()

    def on_actual_size(self):
        self.set_zoom_level(self.default_zoom)

    def on_zoom_in(self):
        self.set_zoom_level(self.get_zoom_level() + 1)

    def on_zoom_out(self):
        self.set_zoom_level(self.get_zoom_level() - 1)

    # FIXME: Remove these once the native menu handlers are restored
    def on_redo(self):
        self.webview.Redo()

    def on_undo(self):
        self.webview.Undo()


class KolibriView(pew.ui.WebUIView, MenuEventHandler):
    def __init__(self, *args, **kwargs):
        super(KolibriView, self).__init__(*args, **kwargs)
        MenuEventHandler.__init__(self)

    def shutdown(self):
        """
        By default, WebUIView assumes a single window, to work the same on mobile and desktops.
        Since we allow for multiple windows, make sure we only really shutdown once all windows are
        closed.
        :return:
        """
        app = pew.ui.get_app()
        if app:
            app.windows.remove(self)
            if len(app.windows) > 0:
                # if we still have open windows, don't run shutdown
                return

        super(KolibriView, self).shutdown()


class Application(pew.ui.PEWApp):
    def __init__(self, *args, **kwargs):
        self.kolibri_service_thread = None
        super().__init__(*args, **kwargs)

    def setUp(self):
        """
        Start your UI and app run loop here.
        """

        # TODO: Generated translated loading screen, or detect language code
        #       and find the closest match like in kolibri-installer-mac.

        loader_page = os.path.abspath(os.path.join(config.DATA_DIR, 'assets', '_load.html'))
        self.loader_url = 'file://{}'.format(loader_page)
        self.kolibri_loaded = False

        self.view = self.create_kolibri_window(self.loader_url)

        self.windows = [self.view]

        # start server
        self.start_server()

        self.load_thread = pew.ui.PEWThread(target=self.wait_for_server)
        self.load_thread.daemon = True
        self.load_thread.start()

        # make sure we show the UI before run completes, as otherwise
        # it is possible the run can complete before the UI is shown,
        # causing the app to shut down early
        self.view.show()

        return 0

    def start_server(self):
        logging.info("Preparing to start Kolibri server...")

        if self.kolibri_service_thread:
            logging.warning("Kolibri service thread is already running")
            self.kolibri_service_thread.stop()

        self.kolibri_service_thread = KolibriServiceThread()
        self.kolibri_service_thread.daemon = True
        self.kolibri_service_thread.start()

    def create_kolibri_window(self, url):
        window = KolibriView("Kolibri", url, delegate=self)

        # create menu bar, we do this per-window for cross-platform purposes
        menu_bar = pew.ui.PEWMenuBar()

        file_menu = pew.ui.PEWMenu(_('File'))
        file_menu.add(_('New Window'), handler=window.on_new_window)
        file_menu.add(_('Close Window'), handler=window.on_close_window)
        file_menu.add_separator()
        file_menu.add(_('Open Kolibri Home Folder'), handler=window.on_open_kolibri_home)

        menu_bar.add_menu(file_menu)

        view_menu = pew.ui.PEWMenu(_('View'))
        view_menu.add(_('Reload'), handler=window.on_reload)
        view_menu.add(_('Actual Size'), handler=window.on_actual_size, shortcut=PEWShortcut('0', modifiers=['CTRL']))
        view_menu.add(_('Zoom In'), handler=window.on_zoom_in, shortcut=PEWShortcut('+', modifiers=['CTRL']))
        view_menu.add(_('Zoom Out'), handler=window.on_zoom_out, shortcut=PEWShortcut('-', modifiers=['CTRL']))
        view_menu.add_separator()
        view_menu.add(_('Open in Browser'), handler=window.on_open_in_browser)
        menu_bar.add_menu(view_menu)

        history_menu = pew.ui.PEWMenu(_('History'))
        history_menu.add(_('Back'), handler=window.on_back, shortcut=PEWShortcut('[', modifiers=['CTRL']))
        history_menu.add(_('Forward'), handler=window.on_forward, shortcut=PEWShortcut(']', modifiers=['CTRL']))
        menu_bar.add_menu(history_menu)

        help_menu = pew.ui.PEWMenu(_('Help'))
        help_menu.add(_('Documentation'), handler=window.on_documentation, shortcut=PEWShortcut('F1'))
        help_menu.add(_('Community Forums'), handler=window.on_forums)
        menu_bar.add_menu(help_menu)

        window.set_menubar(menu_bar)

        return window

    def should_load_url(self, url):
        if url.startswith(KOLIBRI_URL):
            return True
        elif url == self.loader_url and not self.kolibri_loaded:
            return not self.kolibri_loaded
        else:
            subprocess.call(['xdg-open', url])
            return False

        return True

    def page_loaded(self, url):
        """
        This is a PyEverywhere delegate method to let us know the WebView is ready to use.
        """

        # Make sure that any attempts to use back functionality don't take us back to the loading screen
        # For more info, see: https://stackoverflow.com/questions/8103532/how-to-clear-webview-history-in-android
        if not self.kolibri_loaded and url != self.loader_url:
            # FIXME: Change pew to reference the native webview as webview.native_webview rather than webview.webview
            # for clarity.
            self.kolibri_loaded = True
            self.view.clear_history()

    def wait_for_server(self):
        kolibri_responding_event = threading.Event()
        kolibri_poller_thread = KolibriPoller(kolibri_responding_event)

        kolibri_poller_thread.start()

        is_responding = kolibri_responding_event.is_set()
        while not is_responding:
            is_responding = kolibri_responding_event.wait(timeout=None)

        kolibri_poller_thread.stop()

        # Check for saved URL, which exists when the app was put to sleep last time it ran
        saved_state = self.view.get_view_state()
        logging.debug('Persisted View State: {}'.format(self.view.get_view_state()))

        if "URL" in saved_state and saved_state["URL"].startswith(KOLIBRI_URL):
            pew.ui.run_on_main_thread(self.view.load_url, saved_state["URL"])
            return

        pew.ui.run_on_main_thread(self.view.load_url, KOLIBRI_URL)

    def get_main_window(self):
        return self.view

