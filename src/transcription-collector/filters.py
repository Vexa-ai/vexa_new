import re
import logging
import importlib
import os

logger = logging.getLogger("transcription_collector.filters")

# Base non-informative segment patterns to filter out
BASE_NON_INFORMATIVE_PATTERNS = [
    r"^\[BLANK_AUDIO\]$",
    r"^<no audio>$",
    r"^<inaudible>$",
    r"^<>$",
    r"^<3$",
    r"^<3\s*$",
    r"^\s*<3\s*$",
    r"^\s*$",  # Empty or whitespace-only segments
    r"^>+$",   # Just '>' characters
    r"^<+$",   # Just '<' characters
    r"^>>$",   # Just '>>' characters
    r"^<<$",   # Just '<<' characters
]

class TranscriptionFilter:
    """Manages transcription filtering logic"""
    
    def __init__(self):
        self.custom_filters = []
        self.patterns = list(BASE_NON_INFORMATIVE_PATTERNS)
        self.min_character_length = 3
        self.min_real_words = 1
        self.stopwords = {}
        
        # Load configuration
        self.load_config()
    
    def load_config(self):
        """Load filter configuration from filter_config.py"""
        try:
            # Try importing the configuration file
            config = importlib.import_module('filter_config')
            
            # Add additional patterns from config
            if hasattr(config, 'ADDITIONAL_FILTER_PATTERNS'):
                self.patterns.extend(config.ADDITIONAL_FILTER_PATTERNS)
                logger.info(f"Added {len(config.ADDITIONAL_FILTER_PATTERNS)} patterns from config")
            
            # Set minimum character length
            if hasattr(config, 'MIN_CHARACTER_LENGTH'):
                self.min_character_length = config.MIN_CHARACTER_LENGTH
                logger.info(f"Set minimum character length to {self.min_character_length}")
            
            # Set minimum real words
            if hasattr(config, 'MIN_REAL_WORDS'):
                self.min_real_words = config.MIN_REAL_WORDS
                logger.info(f"Set minimum real words to {self.min_real_words}")
            
            # Add custom filter functions
            if hasattr(config, 'CUSTOM_FILTERS'):
                self.custom_filters.extend(config.CUSTOM_FILTERS)
                logger.info(f"Added {len(config.CUSTOM_FILTERS)} custom filter functions")
            
            # Add stopwords
            if hasattr(config, 'STOPWORDS'):
                self.stopwords = config.STOPWORDS
                logger.info(f"Loaded stopwords for {len(config.STOPWORDS)} languages")
                
            logger.info("Successfully loaded filter configuration")
        except ImportError:
            logger.warning("No filter_config.py found, using default settings")
        except Exception as e:
            logger.error(f"Error loading filter configuration: {e}")
    
    def add_custom_filter(self, filter_function):
        """
        Add a custom filter function
        
        Args:
            filter_function: Function that takes text and returns True if it should be kept
        """
        self.custom_filters.append(filter_function)
    
    def is_stop_word(self, word, language='en'):
        """Check if a word is a stopword in the given language"""
        return language in self.stopwords and word.lower() in self.stopwords[language]
    
    def filter_segment(self, text, language='en'):
        """
        Apply all filters to determine if segment should be kept
        
        Args:
            text (str): Text to filter
            language (str): Language code for language-specific filtering
            
        Returns:
            bool: True if segment passes all filters, False otherwise
        """
        # Strip whitespace
        text = text.strip()
        
        # Check minimum length
        if len(text) < self.min_character_length:
            logger.debug(f"Filtering out short text: '{text}'")
            return False
        
        # Check against patterns
        for pattern in self.patterns:
            if re.match(pattern, text):
                logger.debug(f"Filtering out text matching pattern {pattern}: '{text}'")
                return False
        
        # Count actual words (at least 3 characters) - exclude stopwords
        real_words = [
            w for w in text.split() 
            if len(w) >= 3 and 
            not w.startswith('<') and 
            not w.startswith('[') and
            not self.is_stop_word(w, language)
        ]
        
        if len(real_words) < self.min_real_words:
            logger.debug(f"Filtering out text with insufficient real words: '{text}'")
            return False
        
        # Apply any custom filters
        for custom_filter in self.custom_filters:
            try:
                if not custom_filter(text):
                    logger.debug(f"Text filtered by custom filter {custom_filter.__name__}: '{text}'")
                    return False
            except Exception as e:
                logger.error(f"Error in custom filter {custom_filter.__name__}: {e}")
                
        return True 