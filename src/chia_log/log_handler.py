# std
from typing import Optional, List, Type
import logging

# project
from src.chia_log.handlers import LogHandlerInterface
from src.chia_log.handlers.daily_stats.stats_manager import StatsManager
from src.chia_log.handlers.harvester_activity_handler import HarvesterActivityHandler
from src.chia_log.handlers.partial_handler import PartialHandler
from src.chia_log.handlers.block_handler import BlockHandler
from src.chia_log.handlers.finished_signage_point_handler import FinishedSignagePointHandler
from src.chia_log.handlers.wallet_added_coin_handler import WalletAddedCoinHandler
from src.chia_log.log_consumer import LogConsumerSubscriber, LogConsumer
from src.notifier.notify_manager import NotifyManager


def _check_handler_enabled(config: dict, handler_name: str) -> bool:
    """Fallback to True for backwards compatability"""
    try:
        return config[handler_name].get("enable", True)
    except KeyError as key:
        logging.debug(f"Invalid config.yaml. Missing key: {key}")
    return True


class LogHandler(LogConsumerSubscriber):
    """This class holds a list of handlers that analyze
    specific parts of the logs and generate events that
    are consumed by the notifier (for user notifications).

    Data flow:
        LogConsumer -> LogHandler -> Notifier

    Three easy steps to extend monitoring functionality
    1. Create a parser for a new part of the log stream
    2. Create a handler for analysing the parsed information
    3. Add the new handler to the list of handlers below
    """

    def __init__(
        self,
        config: Optional[dict],
        log_consumer: LogConsumer,
        notify_manager: NotifyManager,
        stats_manager: Optional[StatsManager] = None,
    ):
        self._notify_manager = notify_manager
        self._stats_manager = stats_manager

        config = config or {}
        available_handlers: List[Type[LogHandlerInterface]] = [
            HarvesterActivityHandler,
            PartialHandler,
            BlockHandler,
            FinishedSignagePointHandler,
            WalletAddedCoinHandler,
        ]
        self._handlers = []
        for handler in available_handlers:
            if _check_handler_enabled(config, handler.config_name()):
                # With v0.7.1, upstream Chiadog project broke compatibility with old config.yamls
                if handler.config_name() in config:
                    handler_config = config.get()
                else: # Just use a default config with enable=True
                    handler_config = { 'enable': True }
                # Always add in top-level configuration like blockchain prefix and symbol
                handler_config['prefix'] = log_consumer.get_prefix()
                handler_config['symbol'] = log_consumer.get_coin_symbol()
                self._handlers.append(handler(handler_config))
            else:
                logging.info(f"Disabled handler: {handler.config_name()}")

        log_consumer.subscribe(self)

    def consume_logs(self, logs: str):
        for handler in self._handlers:
            events = handler.handle(logs, self._stats_manager)
            self._notify_manager.process_events(events)
