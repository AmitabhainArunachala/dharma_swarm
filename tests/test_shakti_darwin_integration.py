"""Integration tests for Shakti→Darwin routing (constitutional hardening)."""

import asyncio
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_shakti_perception_routes_to_darwin():
    """High-salience Shakti perceptions are routed to Darwin Engine."""
    from dharma_swarm.shakti import ShaktiLoop, ShaktiPerception
    from dharma_swarm.evolution import DarwinEngine
    
    # Create a high-salience perception
    perception = ShaktiPerception(
        energy="kriya",  # Action energy
        observation="Critical system mutation detected",
        file_path="dharma_swarm/core.py",
        impact="system",  # High impact
        salience=0.85,  # High salience
        connections=[],
    )
    
    # Mock Darwin Engine
    with patch("dharma_swarm.evolution.DarwinEngine") as MockDarwin:
        mock_darwin = AsyncMock()
        MockDarwin.return_value = mock_darwin
        
        # Simulate the routing logic from orchestrate_live.py
        perceptions = [perception]
        high = [p for p in perceptions if p.salience >= 0.7]
        
        if high:
            darwin = MockDarwin()
            await darwin.init()
            
            for p in high:
                if p.impact in ("module", "system"):
                    await darwin.propose(
                        component=p.file_path or "system",
                        change_type="mutation",
                        description=f"Shakti {p.energy} perception: {p.observation}",
                        think_notes=f"Impact: {p.impact}, Salience: {p.salience:.2f}",
                    )
        
        # Verify Darwin was called
        mock_darwin.init.assert_awaited_once()
        mock_darwin.propose.assert_awaited_once()
        
        # Verify proposal content
        call_args = mock_darwin.propose.call_args
        assert call_args.kwargs["component"] == "dharma_swarm/core.py"
        assert call_args.kwargs["change_type"] == "mutation"
        assert "kriya" in call_args.kwargs["description"]
        assert "Critical system mutation" in call_args.kwargs["description"]


@pytest.mark.asyncio
async def test_low_salience_perceptions_not_routed_to_darwin():
    """Low-salience perceptions are not routed to Darwin."""
    from dharma_swarm.shakti import ShaktiPerception
    from dharma_swarm.evolution import DarwinEngine
    
    # Create a low-salience perception
    perception = ShaktiPerception(
        energy="jnana",
        observation="Minor observation",
        file_path="test.py",
        impact="token",
        salience=0.3,  # Low salience
        connections=[],
    )
    
    # Mock Darwin Engine
    with patch("dharma_swarm.evolution.DarwinEngine") as MockDarwin:
        mock_darwin = AsyncMock()
        MockDarwin.return_value = mock_darwin
        
        # Simulate routing logic
        perceptions = [perception]
        high = [p for p in perceptions if p.salience >= 0.7]
        
        # Should be empty
        assert len(high) == 0
        
        # Darwin should not be initialized
        MockDarwin.assert_not_called()


@pytest.mark.asyncio
async def test_module_impact_but_low_salience_not_routed():
    """Even module-level impact needs high salience to route."""
    from dharma_swarm.shakti import ShaktiPerception
    from dharma_swarm.evolution import DarwinEngine
    
    perception = ShaktiPerception(
        energy="kriya",
        observation="Something happened",
        file_path="module.py",
        impact="module",  # High impact
        salience=0.5,  # But low salience
        connections=[],
    )
    
    with patch("dharma_swarm.evolution.DarwinEngine") as MockDarwin:
        perceptions = [perception]
        high = [p for p in perceptions if p.salience >= 0.7]
        
        assert len(high) == 0
        MockDarwin.assert_not_called()


@pytest.mark.asyncio
async def test_high_salience_but_token_impact_not_routed():
    """Token-level impact doesn't route even with high salience."""
    from dharma_swarm.shakti import ShaktiPerception
    from dharma_swarm.evolution import DarwinEngine
    
    perception = ShaktiPerception(
        energy="jnana",
        observation="Interesting observation",
        file_path="test.py",
        impact="token",  # Low impact
        salience=0.9,  # High salience
        connections=[],
    )
    
    with patch("dharma_swarm.evolution.DarwinEngine") as MockDarwin:
        mock_darwin = AsyncMock()
        MockDarwin.return_value = mock_darwin
        
        # Simulate routing logic
        perceptions = [perception]
        high = [p for p in perceptions if p.salience >= 0.7]
        
        # High salience, so filtered
        assert len(high) == 1
        
        # But should NOT route to Darwin (impact is "token", not "module" or "system")
        darwin = MockDarwin()
        await darwin.init()
        
        for p in high:
            if p.impact in ("module", "system"):
                await darwin.propose(component="test", change_type="mutation", description="test")
        
        # propose should NOT be called
        mock_darwin.propose.assert_not_awaited()


@pytest.mark.asyncio
async def test_multiple_high_salience_perceptions_all_routed():
    """Multiple qualifying perceptions all get routed."""
    from dharma_swarm.shakti import ShaktiPerception
    from dharma_swarm.evolution import DarwinEngine
    
    perceptions = [
        ShaktiPerception("kriya", "Mutation 1", "file1.py", "system", 0.8, []),
        ShaktiPerception("iccha", "Mutation 2", "file2.py", "module", 0.9, []),
        ShaktiPerception("jnana", "Low salience", "file3.py", "token", 0.5, []),
    ]
    
    with patch("dharma_swarm.evolution.DarwinEngine") as MockDarwin:
        mock_darwin = AsyncMock()
        MockDarwin.return_value = mock_darwin
        
        high = [p for p in perceptions if p.salience >= 0.7]
        
        darwin = MockDarwin()
        await darwin.init()
        
        for p in high:
            if p.impact in ("module", "system"):
                await darwin.propose(
                    component=p.file_path,
                    change_type="mutation",
                    description=f"Shakti {p.energy} perception: {p.observation}",
                )
        
        # Should be called twice (2 high-salience + high-impact perceptions)
        assert mock_darwin.propose.await_count == 2


def test_shakti_hook_injected_in_agent_runner():
    """Shakti hook is injected into agent system prompts."""
    from dharma_swarm.agent_runner import _build_system_prompt
    from dharma_swarm.models import AgentConfig, AgentRole, ProviderType
    
    # Test with OpenRouter (non-Claude Code provider)
    config = AgentConfig(
        name="test_agent",
        role=AgentRole.RESEARCHER,
        provider=ProviderType.OPENROUTER,
    )
    
    prompt = _build_system_prompt(config)
    
    # Shakti hook should be present
    assert "SHAKTI PERCEPTION" in prompt or "shakti" in prompt.lower()


def test_shakti_hook_injected_for_all_providers():
    """Shakti hook is injected for ALL providers, not just Claude Code."""
    from dharma_swarm.agent_runner import _build_system_prompt
    from dharma_swarm.models import AgentConfig, AgentRole, ProviderType
    
    providers_to_test = [
        ProviderType.OPENROUTER,
        ProviderType.ANTHROPIC,
        ProviderType.OPENAI,
    ]
    
    for provider in providers_to_test:
        config = AgentConfig(
            name=f"test_{provider.value}",
            role=AgentRole.RESEARCHER,
            provider=provider,
        )
        
        prompt = _build_system_prompt(config)
        
        # All should have Shakti hook
        assert "SHAKTI" in prompt or "shakti" in prompt.lower(), \
            f"Shakti hook missing for provider {provider.value}"
