import multiprocessing

from ..globals import init_logging


class KolibriServiceStopProcess(multiprocessing.Process):
    """
    Stops Kolibri using the cli command. This runs as a separate process to
    avoid blocking the rest of the program while Kolibri is stopping.
    """

    def __init__(self, context):
        self.__context = context
        super().__init__()

    def run(self):
        if self.__context.is_stopped:
            return
        elif self.__context.await_start_result() != self.__context.StartResult.SUCCESS:
            return

        init_logging("kolibri-daemon-stop.txt")

        from kolibri.utils.cli import stop

        try:
            stop.callback()
        except SystemExit:
            # Kolibri calls sys.exit here, but we don't want to exit
            pass

        self.__context.is_stopped = True
