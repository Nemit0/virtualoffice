"""
Unit tests for ParticipationBalancer

Tests the participation balancing system that ensures realistic distribution
of communication volume across personas.

Requirements tested:
- R-5.1: Track message counts per persona per day
- R-5.2: Throttle personas exceeding 2x team average
- R-5.3: Boost personas below 0.5x team average
- R-9.1: Deterministic behavior with random seed
- R-11.4: Configuration support via enabled flag
"""

import random
import pytest
from src.virtualoffice.sim_manager.participation_balancer import (
    ParticipationBalancer,
    ParticipationStats
)


class TestParticipationBalancerInit:
    """Test ParticipationBalancer initialization."""
    
    def test_init_enabled(self):
        """Test initialization with balancing enabled."""
        balancer = ParticipationBalancer(enabled=True)
        assert balancer.enabled is True
        assert balancer.stats == {}
    
    def test_init_disabled(self):
        """Test initialization with balancing disabled."""
        balancer = ParticipationBalancer(enabled=False)
        assert balancer.enabled is False
        assert balancer.stats == {}
    
    def test_init_default(self):
        """Test initialization with default parameters."""
        balancer = ParticipationBalancer()
        assert balancer.enabled is True


class TestMessageCounting:
    """Test message counting functionality (R-5.1)."""
    
    def test_record_email_message(self):
        """Test recording an email message."""
        balancer = ParticipationBalancer()
        balancer.record_message(1, 0, 'email')
        
        stats = balancer._get_stats(1, 0)
        assert stats.email_count == 1
        assert stats.chat_count == 0
        assert stats.total_count == 1
    
    def test_record_chat_message(self):
        """Test recording a chat message."""
        balancer = ParticipationBalancer()
        balancer.record_message(1, 0, 'chat')
        
        stats = balancer._get_stats(1, 0)
        assert stats.email_count == 0
        assert stats.chat_count == 1
        assert stats.total_count == 1
    
    def test_record_multiple_messages(self):
        """Test recording multiple messages."""
        balancer = ParticipationBalancer()
        balancer.record_message(1, 0, 'email')
        balancer.record_message(1, 0, 'email')
        balancer.record_message(1, 0, 'chat')
        
        stats = balancer._get_stats(1, 0)
        assert stats.email_count == 2
        assert stats.chat_count == 1
        assert stats.total_count == 3
    
    def test_record_messages_different_personas(self):
        """Test recording messages for different personas."""
        balancer = ParticipationBalancer()
        balancer.record_message(1, 0, 'email')
        balancer.record_message(2, 0, 'chat')
        
        stats1 = balancer._get_stats(1, 0)
        stats2 = balancer._get_stats(2, 0)
        
        assert stats1.total_count == 1
        assert stats2.total_count == 1
    
    def test_record_messages_different_days(self):
        """Test recording messages on different days."""
        balancer = ParticipationBalancer()
        balancer.record_message(1, 0, 'email')
        balancer.record_message(1, 1, 'email')
        
        stats_day0 = balancer._get_stats(1, 0)
        stats_day1 = balancer._get_stats(1, 1)
        
        assert stats_day0.total_count == 1
        assert stats_day1.total_count == 1
    
    def test_record_unknown_channel(self):
        """Test recording message with unknown channel."""
        balancer = ParticipationBalancer()
        balancer.record_message(1, 0, 'unknown')
        
        stats = balancer._get_stats(1, 0)
        # Should not increment any count
        assert stats.total_count == 0


class TestTeamAverage:
    """Test team average calculation."""
    
    def test_team_average_no_messages(self):
        """Test team average with no messages."""
        balancer = ParticipationBalancer()
        avg = balancer._get_team_average(0, 10)
        assert avg == 0.0
    
    def test_team_average_single_persona(self):
        """Test team average with single persona."""
        balancer = ParticipationBalancer()
        balancer.record_message(1, 0, 'email')
        balancer.record_message(1, 0, 'chat')
        
        avg = balancer._get_team_average(0, 1)
        assert avg == 2.0
    
    def test_team_average_multiple_personas(self):
        """Test team average with multiple personas."""
        balancer = ParticipationBalancer()
        balancer.record_message(1, 0, 'email')
        balancer.record_message(2, 0, 'email')
        balancer.record_message(2, 0, 'chat')
        
        avg = balancer._get_team_average(0, 2)
        assert avg == 1.5  # (1 + 2) / 2
    
    def test_team_average_zero_team_size(self):
        """Test team average with zero team size."""
        balancer = ParticipationBalancer()
        balancer.record_message(1, 0, 'email')
        
        avg = balancer._get_team_average(0, 0)
        assert avg == 0.0


class TestThrottlingBoostingLogic:
    """Test throttling and boosting logic (R-5.2, R-5.3)."""
    
    def test_throttle_high_volume_sender(self):
        """Test throttling for persona exceeding 2x team average."""
        balancer = ParticipationBalancer(enabled=True)
        
        # Create high volume sender (20 messages)
        for _ in range(20):
            balancer.record_message(1, 0, 'email')
        
        # Create normal senders (5 messages each)
        for pid in range(2, 11):
            for _ in range(5):
                balancer.record_message(pid, 0, 'email')
        
        # Team average = (20 + 9*5) / 10 = 6.5
        # Person 1 ratio = 20 / 6.5 = 3.08 > 2.0
        probability = balancer.get_send_probability(1, 0, 10)
        assert probability == 0.3  # Throttled
    
    def test_boost_low_volume_sender(self):
        """Test boosting for persona below 0.5x team average."""
        balancer = ParticipationBalancer(enabled=True)
        
        # Create low volume sender (1 message)
        balancer.record_message(1, 0, 'email')
        
        # Create normal senders (10 messages each)
        for pid in range(2, 11):
            for _ in range(10):
                balancer.record_message(pid, 0, 'email')
        
        # Team average = (1 + 9*10) / 10 = 9.1
        # Person 1 ratio = 1 / 9.1 = 0.11 < 0.5
        probability = balancer.get_send_probability(1, 0, 10)
        assert probability == 0.9  # Boosted
    
    def test_normal_volume_sender(self):
        """Test normal probability for persona within range."""
        balancer = ParticipationBalancer(enabled=True)
        
        # Create personas with equal message counts
        for pid in range(1, 11):
            for _ in range(5):
                balancer.record_message(pid, 0, 'email')
        
        # Team average = 5, ratio = 1.0 (within 0.5 to 2.0)
        probability = balancer.get_send_probability(1, 0, 10)
        assert probability == 0.6  # Normal
    
    def test_disabled_always_returns_one(self):
        """Test that disabled balancer always returns 1.0 (R-11.4)."""
        balancer = ParticipationBalancer(enabled=False)
        
        # Create high volume sender
        for _ in range(20):
            balancer.record_message(1, 0, 'email')
        
        # Should return 1.0 even though volume is high
        probability = balancer.get_send_probability(1, 0, 10)
        assert probability == 1.0


class TestDeterministicBehavior:
    """Test deterministic behavior with random seed (R-9.1)."""
    
    def test_should_generate_fallback_deterministic(self):
        """Test that same seed produces same results."""
        balancer = ParticipationBalancer(enabled=True)
        
        # Run with seed 42
        rng1 = random.Random(42)
        results1 = []
        for _ in range(10):
            result = balancer.should_generate_fallback(1, 0, 10, rng1)
            results1.append(result)
        
        # Run again with same seed
        rng2 = random.Random(42)
        results2 = []
        for _ in range(10):
            result = balancer.should_generate_fallback(1, 0, 10, rng2)
            results2.append(result)
        
        assert results1 == results2
    
    def test_should_generate_fallback_different_seeds(self):
        """Test that different seeds produce different results."""
        balancer = ParticipationBalancer(enabled=True)
        
        # Run with seed 42
        rng1 = random.Random(42)
        results1 = []
        for _ in range(100):
            result = balancer.should_generate_fallback(1, 0, 10, rng1)
            results1.append(result)
        
        # Run with seed 123
        rng2 = random.Random(123)
        results2 = []
        for _ in range(100):
            result = balancer.should_generate_fallback(1, 0, 10, rng2)
            results2.append(result)
        
        # Results should be different (very unlikely to be identical)
        assert results1 != results2
    
    def test_should_generate_fallback_respects_probability(self):
        """Test that decisions respect probability over many trials."""
        balancer = ParticipationBalancer(enabled=True)
        
        # Create high volume sender (should be throttled to 0.3)
        for _ in range(20):
            balancer.record_message(1, 0, 'email')
        
        # Run many trials
        rng = random.Random(42)
        successes = sum(
            1 for _ in range(1000)
            if balancer.should_generate_fallback(1, 0, 10, rng)
        )
        
        # Should be approximately 30% (allow 5% variance)
        success_rate = successes / 1000
        assert 0.25 < success_rate < 0.35


class TestStatsSummary:
    """Test statistics summary functionality."""
    
    def test_get_stats_summary_no_messages(self):
        """Test summary with no messages."""
        balancer = ParticipationBalancer()
        summary = balancer.get_stats_summary(0)
        
        assert summary['total_messages'] == 0
        assert summary['persona_counts'] == []
        assert summary['top_2_percentage'] == 0.0
        assert summary['gini_coefficient'] == 0.0
    
    def test_get_stats_summary_single_persona(self):
        """Test summary with single persona."""
        balancer = ParticipationBalancer()
        balancer.record_message(1, 0, 'email')
        balancer.record_message(1, 0, 'chat')
        
        summary = balancer.get_stats_summary(0)
        
        assert summary['total_messages'] == 2
        assert summary['persona_counts'] == [(1, 2)]
        assert summary['top_2_percentage'] == 100.0
    
    def test_get_stats_summary_multiple_personas(self):
        """Test summary with multiple personas."""
        balancer = ParticipationBalancer()
        
        # Person 1: 10 messages
        for _ in range(10):
            balancer.record_message(1, 0, 'email')
        
        # Person 2: 5 messages
        for _ in range(5):
            balancer.record_message(2, 0, 'email')
        
        # Person 3: 2 messages
        for _ in range(2):
            balancer.record_message(3, 0, 'email')
        
        summary = balancer.get_stats_summary(0)
        
        assert summary['total_messages'] == 17
        assert summary['persona_counts'] == [(1, 10), (2, 5), (3, 2)]
        # Top 2 = (10 + 5) / 17 = 88.2%
        assert 88.0 < summary['top_2_percentage'] < 89.0
    
    def test_get_stats_summary_different_days(self):
        """Test summary for different days."""
        balancer = ParticipationBalancer()
        
        # Day 0
        balancer.record_message(1, 0, 'email')
        
        # Day 1
        balancer.record_message(1, 1, 'email')
        balancer.record_message(1, 1, 'chat')
        
        summary_day0 = balancer.get_stats_summary(0)
        summary_day1 = balancer.get_stats_summary(1)
        
        assert summary_day0['total_messages'] == 1
        assert summary_day1['total_messages'] == 2


class TestGiniCoefficient:
    """Test Gini coefficient calculation."""
    
    def test_gini_perfect_equality(self):
        """Test Gini coefficient with perfect equality."""
        balancer = ParticipationBalancer()
        
        # Everyone sends same amount
        gini = balancer._calculate_gini([5, 5, 5, 5, 5])
        assert gini == 0.0
    
    def test_gini_perfect_inequality(self):
        """Test Gini coefficient with perfect inequality."""
        balancer = ParticipationBalancer()
        
        # One person sends everything
        gini = balancer._calculate_gini([100, 0, 0, 0, 0])
        assert gini >= 0.8  # Very high inequality
    
    def test_gini_moderate_inequality(self):
        """Test Gini coefficient with moderate inequality."""
        balancer = ParticipationBalancer()
        
        # Some inequality
        gini = balancer._calculate_gini([10, 5, 3, 2, 1])
        assert 0.2 < gini < 0.5  # Moderate inequality
    
    def test_gini_empty_list(self):
        """Test Gini coefficient with empty list."""
        balancer = ParticipationBalancer()
        gini = balancer._calculate_gini([])
        assert gini == 0.0
    
    def test_gini_all_zeros(self):
        """Test Gini coefficient with all zeros."""
        balancer = ParticipationBalancer()
        gini = balancer._calculate_gini([0, 0, 0])
        assert gini == 0.0


class TestIntegration:
    """Integration tests for complete workflows."""
    
    def test_full_day_simulation(self):
        """Test a full day of message recording and balancing."""
        balancer = ParticipationBalancer(enabled=True)
        rng = random.Random(42)
        
        # Simulate 10 personas sending messages throughout the day
        for tick in range(100):
            for person_id in range(1, 11):
                # Each persona has 60% chance to send
                if balancer.should_generate_fallback(person_id, 0, 10, rng):
                    channel = 'email' if rng.random() < 0.5 else 'chat'
                    balancer.record_message(person_id, 0, channel)
        
        # Check summary
        summary = balancer.get_stats_summary(0)
        
        # Should have messages
        assert summary['total_messages'] > 0
        
        # Top 2 should be reasonable (not too dominant)
        # With balancing, should be < 50% typically
        assert summary['top_2_percentage'] < 60.0
        
        # Gini should show some equality
        assert summary['gini_coefficient'] < 0.5
    
    def test_multi_day_simulation(self):
        """Test multi-day simulation with separate day tracking."""
        balancer = ParticipationBalancer(enabled=True)
        rng = random.Random(42)
        
        # Simulate 3 days
        for day in range(3):
            for person_id in range(1, 6):
                # Each persona sends 5 messages per day
                for _ in range(5):
                    balancer.record_message(person_id, day, 'email')
        
        # Check each day separately
        for day in range(3):
            summary = balancer.get_stats_summary(day)
            assert summary['total_messages'] == 25  # 5 personas * 5 messages
            assert summary['top_2_percentage'] == 40.0  # 2/5 = 40%
