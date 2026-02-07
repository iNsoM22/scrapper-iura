from abc import ABC, abstractmethod

class BaseScraper(ABC):
    @abstractmethod
    def connect(self):
        """Connects to the browser instance."""
        pass

    @abstractmethod
    def scrape(self):
        """Main scraping logic."""
        pass

    @abstractmethod
    def close(self):
        """Closes the connection."""
        pass
