"""
Main Application: TrendBot main entry point.
Initializes all components using the ApplicationFactory pattern.
"""
import signal
import sys
from core.application_factory import ApplicationFactory
from core.exceptions import TrendBotException
from utils.logger import LoggerManager


class TrendBot:
    """Main application class."""
    
    def __init__(self):
        """Initializes TrendBot."""
        self.components = None
        self.logger = None
        self._setup_signal_handlers()
    
    def _setup_signal_handlers(self) -> None:
        """Sets up signal handlers."""
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame) -> None:
        """
        Signal handler.
        
        Args:
            signum: Signal number
            frame: Frame object
        """
        if self.logger:
            self.logger.info(f"Signal {signum} received, shutting down application...")
        
        self.shutdown()
        sys.exit(0)
    
    def initialize(self) -> None:
        """Initializes all components."""
        print("🚀 Starting TrendBot...")
        
        try:
            # Create components with ApplicationFactory
            factory = ApplicationFactory()
            self.components = factory.create_application()
            
            # Get Logger
            self.logger = self.components['logger']
            
            self.logger.info("=" * 50)
            self.logger.info("Starting TrendBot")
            self.logger.info("=" * 50)
            
            # Initialize Bot
            self.components['telegram_bot'].initialize()
            
            # Start Scheduler
            self.components['scheduler'].start()
            
            # Start Signal scanner scheduler
            self.components['signal_scanner_scheduler'].start()
            
            # Start Signal tracker scheduler
            self.components['signal_tracker_scheduler'].start()
            
            self.logger.info("All components initialized successfully")
            
        except Exception as e:
            error_msg = f"Application initialization error: {str(e)}"
            print(f"❌ {error_msg}")
            if self.logger:
                self.logger.error(error_msg, exc_info=True)
            raise TrendBotException(error_msg)
    
    def run(self) -> None:
        """Runs the bot."""
        if not self.components:
            raise TrendBotException("Application not initialized")
        
        try:
            self.logger.info("Running TrendBot...")
            self.components['telegram_bot'].run()
        except KeyboardInterrupt:
            self.logger.info("Stopped by user")
        except Exception as e:
            error_msg = f"Bot execution error: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            raise TrendBotException(error_msg)
        finally:
            self.shutdown()
    
    def shutdown(self) -> None:
        """Safely shuts down the application."""
        # Pre-shutdown channel notification (before event loop closes)
        try:
            if self.components and 'config' in self.components:
                ch_id = self.components['config'].telegram_channel_id
                msg = "🛑 Bot is shutting down"
                self.logger.info(msg)
                # PTB might be closed; send directly via Telegram HTTP API
                try:
                    import json as _json, urllib.request as _urlreq
                    token = self.components['config'].telegram_token
                    api_url = f"https://api.telegram.org/bot{token}/sendMessage"
                    payload = _json.dumps({'chat_id': ch_id, 'text': msg}).encode('utf-8')
                    req = _urlreq.Request(api_url, data=payload, headers={'Content-Type': 'application/json'})
                    _urlreq.urlopen(req, timeout=5)
                    if self.logger:
                        self.logger.info("Channel message sent (pre-shutdown, direct API)")
                except Exception as http_err:
                    if self.logger:
                        self.logger.error(f"Pre-shutdown direct API error: {http_err}")
        except Exception as e:
            if self.logger:
                self.logger.error(f"Could not send pre-shutdown message: {str(e)}", exc_info=True)
        if self.components and 'scheduler' in self.components:
            try:
                self.components['scheduler'].stop()
                if self.logger:
                    self.logger.info("Scheduler stopped")
            except Exception as e:
                if self.logger:
                    self.logger.error(f"Scheduler stop error: {str(e)}")
        
        if self.components and 'signal_scanner_scheduler' in self.components:
            try:
                self.components['signal_scanner_scheduler'].stop()
                if self.logger:
                    self.logger.info("Signal scanner scheduler stopped")
            except Exception as e:
                if self.logger:
                    self.logger.error(f"Signal scanner scheduler stop error: {str(e)}")
        
        if self.components and 'signal_tracker_scheduler' in self.components:
            try:
                self.components['signal_tracker_scheduler'].stop()
                if self.logger:
                    self.logger.info("Signal tracker scheduler stopped")
            except Exception as e:
                if self.logger:
                    self.logger.error(f"Signal tracker scheduler stop error: {str(e)}")
        
        if self.logger:
            self.logger.info("TrendBot shut down")


def main():
    """Main function."""
    try:
        bot = TrendBot()
        bot.initialize()
        bot.run()
    except TrendBotException as e:
        print(f"❌ TrendBot Error: {e.message}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected Error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
