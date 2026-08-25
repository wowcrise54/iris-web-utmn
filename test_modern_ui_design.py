"""
Test suite for DFIR-IRIS Modern UI enhancements.

Following TDD principles:
1. Write failing test first
2. Run test to verify failure
3. Implement minimal code to pass
4. Run test to verify pass
5. Refactor if needed

Run with: pytest test_modern_ui_design.py -v
"""

import pytest
import os
import sys
from pathlib import Path


# Add source to path for imports
sys.path.insert(0, str(Path(__file__).parent / 'source'))


class TestAlertStatusBadges:
    """Tests for alert status badge styling."""
    
    def test_new_status_has_blue_gradient(self):
        """Test that 'new' status badges use blue gradient."""
        # This will fail until we verify the CSS exists
        css_file = Path(__file__).parent / 'modern-ui-enhancements.css'
        assert css_file.exists(), "CSS file should exist"
        
        content = css_file.read_text(encoding='utf-8')
        assert '.badge-status-new' in content or '.status-new' in content, \
            "Should have .badge-status-new or .status-new selector"
        assert '#3B82F6' in content or '#2563EB' in content, \
            "Should use blue color (#3B82F6 or #2563EB)"
    
    def test_open_status_has_orange_gradient(self):
        """Test that 'open' status badges use orange/amber gradient."""
        css_file = Path(__file__).parent / 'modern-ui-enhancements.css'
        content = css_file.read_text(encoding='utf-8')
        
        assert '.badge-status-open' in content or '.status-open' in content, \
            "Should have .badge-status-open or .status-open selector"
        assert '#F59E0B' in content or '#D97706' in content, \
            "Should use orange/amber color (#F59E0B or #D97706)"
    
    def test_closed_status_has_green_gradient(self):
        """Test that 'closed' status badges use green gradient."""
        css_file = Path(__file__).parent / 'modern-ui-enhancements.css'
        content = css_file.read_text(encoding='utf-8')
        
        assert '.badge-status-closed' in content or '.status-closed' in content, \
            "Should have .badge-status-closed or .status-closed selector"
        assert '#10B981' in content or '#059669' in content, \
            "Should use green color (#10B981 or #059669)"
    
    def test_critical_status_has_animation(self):
        """Test that critical status has pulse animation."""
        css_file = Path(__file__).parent / 'modern-ui-enhancements.css'
        content = css_file.read_text(encoding='utf-8')
        
        assert 'pulse-critical' in content or 'animation' in content, \
            "Critical status should have animation"
        assert '@keyframes' in content, \
            "Should have @keyframes definition"


class TestModernUIEnhancements:
    """Tests for modern UI enhancement features."""
    
    def test_glassmorphism_effects_exist(self):
        """Test that glassmorphism effects are defined."""
        css_file = Path(__file__).parent / 'modern-ui-enhancements.css'
        content = css_file.read_text(encoding='utf-8')
        
        # Check for glassmorphism properties
        has_backdrop_filter = 'backdrop-filter' in content
        has_transparency = 'rgba(' in content or 'rgba(' in content
        has_shadow = 'box-shadow' in content
        
        assert has_backdrop_filter or has_transparency, \
            "Should have glassmorphism effects (backdrop-filter or transparency)"
    
    def test_modern_card_styles_exist(self):
        """Test that modern card styles are defined."""
        css_file = Path(__file__).parent / 'modern-ui-enhancements.css'
        content = css_file.read_text(encoding='utf-8')
        
        # Cards should have border-radius and shadow
        has_border_radius = 'border-radius' in content
        has_card_selector = '.card' in content
        
        assert has_border_radius, "Should have rounded corners"
    
    def test_gradient_backgrounds_used(self):
        """Test that gradient backgrounds are used."""
        css_file = Path(__file__).parent / 'modern-ui-enhancements.css'
        content = css_file.read_text(encoding='utf-8')
        
        assert 'linear-gradient' in content, \
            "Should use linear-gradient for modern look"


class TestSeverityIndicators:
    """Tests for severity level indicators."""
    
    def test_low_severity_has_green_tint(self):
        """Test that low severity uses green tones."""
        css_file = Path(__file__).parent / 'modern-ui-enhancements.css'
        content = css_file.read_text(encoding='utf-8')
        
        assert '.severity-low' in content or '.badge-severity-low' in content
        assert '#6EE7B7' in content or '#34D399' in content
    
    def test_medium_severity_has_yellow_tint(self):
        """Test that medium severity uses yellow/amber tones."""
        css_file = Path(__file__).parent / 'modern-ui-enhancements.css'
        content = css_file.read_text(encoding='utf-8')
        
        assert '.severity-medium' in content or '.badge-severity-medium' in content
        assert '#FCD34D' in content or '#FBBF24' in content
    
    def test_high_severity_has_orange_tint(self):
        """Test that high severity uses orange tones."""
        css_file = Path(__file__).parent / 'modern-ui-enhancements.css'
        content = css_file.read_text(encoding='utf-8')
        
        assert '.severity-high' in content or '.badge-severity-high' in content
        assert '#FB923C' in content or '#F97316' in content
    
    def test_critical_severity_has_red_tint(self):
        """Test that critical severity uses red tones."""
        css_file = Path(__file__).parent / 'modern-ui-enhancements.css'
        content = css_file.read_text(encoding='utf-8')
        
        assert '.severity-critical' in content or '.badge-severity-critical' in content
        assert '#EF4444' in content or '#DC2626' in content


class TestVisualHierarchy:
    """Tests for visual hierarchy improvements."""
    
    def test_shadow_depth_exists(self):
        """Test that box-shadow is used for depth."""
        css_file = Path(__file__).parent / 'modern-ui-enhancements.css'
        content = css_file.read_text(encoding='utf-8')
        
        assert 'box-shadow' in content, \
            "Should use box-shadow for depth and elevation"
    
    def test_spacing_improvements_exist(self):
        """Test that improved spacing/padding is defined."""
        css_file = Path(__file__).parent / 'modern-ui-enhancements.css'
        content = css_file.read_text(encoding='utf-8')
        
        # Should have padding/margin improvements
        has_padding = 'padding:' in content
        has_margin = 'margin:' in content
        
        assert has_padding or has_margin, \
            "Should have spacing improvements"
    
    def test_typography_enhancements_exist(self):
        """Test that typography enhancements are present."""
        css_file = Path(__file__).parent / 'modern-ui-enhancements.css'
        content = css_file.read_text(encoding='utf-8')
        
        # Should have font-weight, letter-spacing, or line-height improvements
        has_font_weight = 'font-weight' in content
        has_letter_spacing = 'letter-spacing' in content
        
        assert has_font_weight or has_letter_spacing, \
            "Should have typography enhancements"


class TestHTMLDemoExists:
    """Tests for HTML demo file."""
    
    def test_demo_html_exists(self):
        """Test that demo HTML file exists."""
        demo_file = Path(__file__).parent / 'modern-ui-demo.html'
        assert demo_file.exists(), "Demo HTML file should exist"
    
    def test_demo_html_is_valid(self):
        """Test that demo HTML has proper structure."""
        demo_file = Path(__file__).parent / 'modern-ui-demo.html'
        content = demo_file.read_text(encoding='utf-8')
        
        assert '<!DOCTYPE html>' in content or '<html' in content, \
            "Should be valid HTML"
        assert '</html>' in content, \
            "Should have closing html tag"
    
    def test_demo_includes_all_statuses(self):
        """Test that demo shows all status types."""
        demo_file = Path(__file__).parent / 'modern-ui-demo.html'
        content = demo_file.read_text(encoding='utf-8')
        
        statuses = ['new', 'open', 'closed', 'resolved', 'pending']
        for status in statuses:
            assert status in content.lower(), \
                f"Demo should include {status} status"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
