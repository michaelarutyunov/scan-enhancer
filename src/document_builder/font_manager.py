"""Font Manager Module

Handles font registration, Cyrillic support, and font fallback chains.
"""
import os
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


class FontManager:
    """Manages font registration and provides Cyrillic-compatible fonts.

    This class handles:
    - Font path lookups across multiple system locations
    - Font registration with ReportLab
    - Cyrillic character support
    - Font fallback chains (DejaVu → Liberation → Arial → Helvetica)
    - Bold variant registration

    Attributes:
        font_name: Name of the registered regular font (e.g., 'DejaVuSans' or 'Helvetica')
        font_name_bold: Name of the registered bold font (e.g., 'DejaVuSans-Bold' or 'Helvetica-Bold')
    """

    def __init__(self):
        """Initialize FontManager and register Cyrillic-compatible fonts."""
        self.font_name = 'Helvetica'  # Default fallback
        self.font_name_bold = 'Helvetica-Bold'  # Bold fallback
        self._setup_fonts()

    def _setup_fonts(self):
        """
        Register fonts that support Cyrillic characters.

        Tries multiple font paths in order of preference:
        1. Bundled DejaVu Sans (in fonts/ directory)
        2. DejaVu Sans (Linux system paths)
        3. Liberation Sans (Linux)
        4. Arial Unicode (macOS)
        5. Arial (Windows)

        Falls back to Helvetica if no fonts are found.
        WARNING: Helvetica does NOT support Cyrillic characters!

        Also registers bold variant if available.
        """
        # Bundled font path (highest priority)
        bundled_font = os.path.join(os.path.dirname(__file__), '..', '..', 'fonts', 'DejaVuSans.ttf')
        bundled_bold_font = os.path.join(os.path.dirname(__file__), '..', '..', 'fonts', 'DejaVuSans-Bold.ttf')

        # Try to register DejaVu Sans (common on Linux)
        font_paths = [
            bundled_font,  # Bundled font (failsafe)
            '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
            '/usr/share/fonts/dejavu/DejaVuSans.ttf',
            '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
            '/System/Library/Fonts/Supplemental/Arial Unicode.ttf',  # macOS
            'C:\\Windows\\Fonts\\arial.ttf',  # Windows
        ]

        # Bold font paths
        bold_font_paths = [
            bundled_bold_font,
            '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
            '/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf',
        ]

        font_found = False

        print("DEBUG: Setting up fonts for Cyrillic support...")
        for font_path in font_paths:
            print(f"DEBUG: Checking font path: {font_path}")
            if os.path.exists(font_path):
                try:
                    pdfmetrics.registerFont(TTFont('DejaVuSans', font_path))
                    self.font_name = 'DejaVuSans'
                    font_found = True
                    print(f"DEBUG: Successfully registered font from: {font_path}")
                    break
                except Exception as e:
                    print(f"DEBUG: Failed to register font {font_path}: {e}")
                    continue

        # Try to register bold font
        bold_font_found = False
        if font_found:
            for bold_font_path in bold_font_paths:
                print(f"DEBUG: Checking bold font path: {bold_font_path}")
                if os.path.exists(bold_font_path):
                    try:
                        pdfmetrics.registerFont(TTFont('DejaVuSans-Bold', bold_font_path))
                        self.font_name_bold = 'DejaVuSans-Bold'
                        bold_font_found = True
                        print(f"DEBUG: Successfully registered bold font from: {bold_font_path}")
                        break
                    except Exception as e:
                        print(f"DEBUG: Failed to register bold font {bold_font_path}: {e}")
                        continue

        if not font_found:
            print("=" * 60)
            print("WARNING: No Cyrillic-compatible font found!")
            print("WARNING: Using Helvetica fallback - Cyrillic text will NOT render correctly!")
            print("WARNING: Install fonts-dejavu-core or add DejaVuSans.ttf to fonts/ directory")
            print("=" * 60)
        elif not bold_font_found:
            print("=" * 60)
            print("WARNING: Bold font not found, using regular font for bold text")
            print("=" * 60)
            self.font_name_bold = self.font_name

    def get_font_name(self, bold: bool = False) -> str:
        """
        Get the registered font name.

        Args:
            bold: If True, return the bold variant; otherwise return regular font

        Returns:
            Font name string suitable for use with ReportLab (e.g., 'DejaVuSans')
        """
        return self.font_name_bold if bold else self.font_name
