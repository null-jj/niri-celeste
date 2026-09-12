import json
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]


def luminance(color):
    rgb = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in rgb]
    return sum(a * b for a, b in zip(linear, (0.2126, 0.7152, 0.0722)))


class ProfileTests(unittest.TestCase):
    def test_text_pairs_have_readable_contrast_in_both_modes(self):
        theme = json.loads((ROOT / 'themes/celeste/theme.json').read_text())
        for mode in ('dark', 'light'):
            for background, foreground in [('primary', 'primaryText'), ('surface', 'surfaceText'),
                                           ('surfaceVariant', 'surfaceVariantText'), ('background', 'backgroundText')]:
                high, low = sorted([luminance(theme[mode][foreground]), luminance(theme[mode][background])], reverse=True)
                with self.subTest(mode=mode, foreground=foreground):
                    self.assertGreaterEqual((high + 0.05) / (low + 0.05), 4.5)

    def test_portable_profile_avoids_personal_session_data(self):
        profile = json.loads((ROOT / 'profile/settings.json').read_text())
        self.assertEqual(profile['customThemeFile'], '@THEME@')
        self.assertFalse(profile['runDmsMatugenTemplates'])
        self.assertFalse(profile['runUserMatugenTemplates'])
        for key in ('wallpaperPath', 'weatherCoordinates', 'weatherLocation', 'niriOutputSettings',
                    'launcherQueryHistory', 'vpnLastConnected'):
            self.assertNotIn(key, profile)
        for bar in profile['barConfigs']:
            self.assertEqual(bar['screenPreferences'], ['all'])

    def test_wallpaper_is_self_contained_vector(self):
        root = ET.parse(ROOT / 'wallpapers/celeste.svg').getroot()
        self.assertEqual(root.tag, '{http://www.w3.org/2000/svg}svg')
        for node in root.iter():
            self.assertNotIn(node.tag.rsplit('}', 1)[-1], ('script', 'image', 'foreignObject'))
            for key, value in node.attrib.items():
                if key.rsplit('}', 1)[-1] == 'href':
                    self.assertTrue(value.startswith('#'))


if __name__ == '__main__':
    unittest.main()
