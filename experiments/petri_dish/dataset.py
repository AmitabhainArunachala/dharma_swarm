"""Ground truth dataset for the Petri Dish experiment.

80 text snippets with manually assigned labels for sentiment, topic, urgency.
Embedded directly — no external files needed.
"""

from __future__ import annotations

import random

from .models import TextSnippet

DATASET: list[TextSnippet] = [
    # --- TECHNOLOGY ---
    TextSnippet(text="The new quantum processor achieved 1000-qubit coherence, but the error rate remains too high for practical use.", true_sentiment="neutral", true_topic="technology", true_urgency="low"),
    TextSnippet(text="Our cloud servers have been down for six hours and customers are unable to access their data.", true_sentiment="negative", true_topic="technology", true_urgency="high"),
    TextSnippet(text="The latest smartphone release features an incredible camera system that photographers are raving about.", true_sentiment="positive", true_topic="technology", true_urgency="low"),
    TextSnippet(text="A critical security vulnerability was found in the widely used OpenSSL library affecting millions of servers.", true_sentiment="negative", true_topic="technology", true_urgency="high"),
    TextSnippet(text="The new programming language gained 50,000 GitHub stars in its first week.", true_sentiment="positive", true_topic="technology", true_urgency="low"),
    TextSnippet(text="Battery technology improvements have plateaued, with no major breakthroughs expected this decade.", true_sentiment="negative", true_topic="technology", true_urgency="low"),
    TextSnippet(text="The AI chip startup just closed a $2 billion funding round, the largest in semiconductor history.", true_sentiment="positive", true_topic="technology", true_urgency="low"),
    TextSnippet(text="Engineers report the autonomous vehicle software update has introduced a dangerous braking bug that needs immediate patching.", true_sentiment="negative", true_topic="technology", true_urgency="high"),
    TextSnippet(text="The open-source database project released version 15 with modest performance improvements.", true_sentiment="neutral", true_topic="technology", true_urgency="low"),
    TextSnippet(text="Several major tech companies announced layoffs totaling 30,000 employees this quarter.", true_sentiment="negative", true_topic="technology", true_urgency="medium"),

    # --- SCIENCE ---
    TextSnippet(text="Researchers discovered a new species of deep-sea fish that produces its own light through bioluminescence.", true_sentiment="positive", true_topic="science", true_urgency="low"),
    TextSnippet(text="The clinical trial for the new Alzheimer's drug showed a 35% reduction in cognitive decline.", true_sentiment="positive", true_topic="science", true_urgency="medium"),
    TextSnippet(text="Arctic ice measurements show the fastest melt rate ever recorded, exceeding worst-case projections.", true_sentiment="negative", true_topic="science", true_urgency="high"),
    TextSnippet(text="The Mars rover collected soil samples that contain trace organic molecules of unknown origin.", true_sentiment="neutral", true_topic="science", true_urgency="medium"),
    TextSnippet(text="A peer review found significant methodological flaws in the widely cited nutrition study.", true_sentiment="negative", true_topic="science", true_urgency="medium"),
    TextSnippet(text="The fusion reactor prototype sustained plasma for 8 minutes, doubling the previous record.", true_sentiment="positive", true_topic="science", true_urgency="low"),
    TextSnippet(text="New satellite data confirms ocean temperatures have risen 0.5 degrees in just three years.", true_sentiment="negative", true_topic="science", true_urgency="high"),
    TextSnippet(text="The genome editing technique was successfully used to correct a genetic disorder in mice.", true_sentiment="positive", true_topic="science", true_urgency="medium"),
    TextSnippet(text="Three independent labs failed to replicate the superconductor claims from last year.", true_sentiment="negative", true_topic="science", true_urgency="low"),
    TextSnippet(text="Astronomers detected an unusual radio signal from a nearby star system that warrants further investigation.", true_sentiment="neutral", true_topic="science", true_urgency="medium"),

    # --- POLITICS ---
    TextSnippet(text="The trade agreement between the two nations was signed after five years of negotiations, boosting both economies.", true_sentiment="positive", true_topic="politics", true_urgency="medium"),
    TextSnippet(text="Voter turnout in the municipal election hit a record low of 18%, raising concerns about democratic engagement.", true_sentiment="negative", true_topic="politics", true_urgency="medium"),
    TextSnippet(text="The parliament passed the infrastructure bill with bipartisan support after months of debate.", true_sentiment="positive", true_topic="politics", true_urgency="low"),
    TextSnippet(text="Tensions between the neighboring countries escalated after military forces were deployed to the border region.", true_sentiment="negative", true_topic="politics", true_urgency="high"),
    TextSnippet(text="The new education policy allocates additional funding to rural schools but critics say it's not enough.", true_sentiment="neutral", true_topic="politics", true_urgency="low"),
    TextSnippet(text="Corruption charges were filed against three senior government officials following a two-year investigation.", true_sentiment="negative", true_topic="politics", true_urgency="medium"),
    TextSnippet(text="The peace negotiations have stalled, with both sides refusing to make concessions on territorial claims.", true_sentiment="negative", true_topic="politics", true_urgency="high"),
    TextSnippet(text="The city council unanimously approved the new public transit expansion plan.", true_sentiment="positive", true_topic="politics", true_urgency="low"),
    TextSnippet(text="Election officials confirmed the results were accurate after a comprehensive audit of all ballots.", true_sentiment="neutral", true_topic="politics", true_urgency="medium"),
    TextSnippet(text="Emergency legislation was drafted to address the housing crisis affecting thousands of families.", true_sentiment="neutral", true_topic="politics", true_urgency="high"),

    # --- CULTURE ---
    TextSnippet(text="The independent film won three major awards at the festival, surprising critics who had dismissed it.", true_sentiment="positive", true_topic="culture", true_urgency="low"),
    TextSnippet(text="The museum's new exhibition on ancient civilizations drew record attendance in its opening week.", true_sentiment="positive", true_topic="culture", true_urgency="low"),
    TextSnippet(text="The beloved author's final novel was published posthumously to mixed reviews from literary critics.", true_sentiment="neutral", true_topic="culture", true_urgency="low"),
    TextSnippet(text="Concert ticket prices have tripled in five years, pricing out many young music fans.", true_sentiment="negative", true_topic="culture", true_urgency="medium"),
    TextSnippet(text="The streaming platform cancelled several popular shows despite strong viewership numbers.", true_sentiment="negative", true_topic="culture", true_urgency="low"),
    TextSnippet(text="A street artist's mural addressing climate change went viral, sparking global conversations online.", true_sentiment="positive", true_topic="culture", true_urgency="low"),
    TextSnippet(text="The traditional craft festival has been running for 200 years without interruption until the pandemic.", true_sentiment="neutral", true_topic="culture", true_urgency="low"),
    TextSnippet(text="Libraries across the country report a 40% increase in book borrowing since launching digital catalogs.", true_sentiment="positive", true_topic="culture", true_urgency="low"),
    TextSnippet(text="The national theatre company faces closure unless emergency funding is secured within the month.", true_sentiment="negative", true_topic="culture", true_urgency="high"),
    TextSnippet(text="The podcast about everyday philosophy became the most downloaded show in its category this year.", true_sentiment="positive", true_topic="culture", true_urgency="low"),

    # --- OTHER ---
    TextSnippet(text="Morning commute times have decreased by 15 minutes on average since the new highway lanes opened.", true_sentiment="positive", true_topic="other", true_urgency="low"),
    TextSnippet(text="The recall affects 2 million vehicles due to a faulty airbag sensor that could fail during deployment.", true_sentiment="negative", true_topic="other", true_urgency="high"),
    TextSnippet(text="The weather forecast predicts moderate temperatures and partly cloudy skies for the rest of the week.", true_sentiment="neutral", true_topic="other", true_urgency="low"),
    TextSnippet(text="A fire at the chemical plant has forced evacuation of nearby neighborhoods and air quality alerts.", true_sentiment="negative", true_topic="other", true_urgency="high"),
    TextSnippet(text="The new community garden program has enrolled 500 families in its first month of operation.", true_sentiment="positive", true_topic="other", true_urgency="low"),
    TextSnippet(text="Food prices rose 8% this quarter, outpacing wage growth and straining household budgets.", true_sentiment="negative", true_topic="other", true_urgency="high"),
    TextSnippet(text="The city's recycling rate improved from 30% to 45% after implementing the new sorting system.", true_sentiment="positive", true_topic="other", true_urgency="low"),
    TextSnippet(text="The bridge inspection revealed structural weaknesses that require immediate repair before winter.", true_sentiment="negative", true_topic="other", true_urgency="high"),
    TextSnippet(text="Annual tourism numbers returned to pre-pandemic levels for the first time since 2019.", true_sentiment="positive", true_topic="other", true_urgency="low"),
    TextSnippet(text="The local farmers market expanded to include vendors from three additional counties.", true_sentiment="positive", true_topic="other", true_urgency="low"),

    # --- TRICKY / EDGE CASES (sarcasm, ambiguity, mixed signals) ---
    TextSnippet(text="Oh great, another social media platform. Just what the world needed.", true_sentiment="negative", true_topic="technology", true_urgency="low"),
    TextSnippet(text="The company's profits soared while employee satisfaction surveys hit an all-time low.", true_sentiment="negative", true_topic="other", true_urgency="medium"),
    TextSnippet(text="The vaccine rollout is ahead of schedule but supply chain issues may cause delays next month.", true_sentiment="neutral", true_topic="science", true_urgency="medium"),
    TextSnippet(text="What a surprise — the billionaire's charitable foundation primarily benefits his own businesses.", true_sentiment="negative", true_topic="politics", true_urgency="low"),
    TextSnippet(text="The renovation of the historic building preserved its character while adding modern accessibility features.", true_sentiment="positive", true_topic="culture", true_urgency="low"),
    TextSnippet(text="Scientists are cautiously optimistic about the results but warn that larger trials are needed.", true_sentiment="neutral", true_topic="science", true_urgency="medium"),
    TextSnippet(text="The startup claims revolutionary AI capabilities, but independent benchmarks tell a different story.", true_sentiment="negative", true_topic="technology", true_urgency="low"),
    TextSnippet(text="After years of decline, the endangered species population has stabilized — though recovery remains uncertain.", true_sentiment="neutral", true_topic="science", true_urgency="medium"),
    TextSnippet(text="The app update fixed the crashing bug but introduced three new ones that are even more annoying.", true_sentiment="negative", true_topic="technology", true_urgency="medium"),
    TextSnippet(text="Unemployment numbers dropped slightly, though economists note the figures don't capture underemployment.", true_sentiment="neutral", true_topic="politics", true_urgency="medium"),

    # --- ADDITIONAL BALANCE ---
    TextSnippet(text="The hospital's new emergency response protocol reduced average wait times by 40%.", true_sentiment="positive", true_topic="other", true_urgency="medium"),
    TextSnippet(text="The wildfire has consumed 50,000 acres and is only 10% contained with winds expected to increase.", true_sentiment="negative", true_topic="other", true_urgency="high"),
    TextSnippet(text="Researchers found that regular meditation practice correlates with measurable changes in brain structure.", true_sentiment="positive", true_topic="science", true_urgency="low"),
    TextSnippet(text="The proposed data privacy law would give citizens the right to delete all personal data held by companies.", true_sentiment="neutral", true_topic="politics", true_urgency="medium"),
    TextSnippet(text="The orchestra's free outdoor concert series brought classical music to underserved neighborhoods.", true_sentiment="positive", true_topic="culture", true_urgency="low"),
    TextSnippet(text="A ransomware attack on the hospital network has forced staff to revert to paper records immediately.", true_sentiment="negative", true_topic="technology", true_urgency="high"),
    TextSnippet(text="The international aid package was approved but logistical challenges may delay delivery for weeks.", true_sentiment="neutral", true_topic="politics", true_urgency="high"),
    TextSnippet(text="The Nobel Prize committee announced this year's laureates, recognizing groundbreaking work in protein folding.", true_sentiment="positive", true_topic="science", true_urgency="low"),
    TextSnippet(text="Construction of the affordable housing project is 6 months behind schedule and over budget.", true_sentiment="negative", true_topic="other", true_urgency="medium"),
    TextSnippet(text="The documentary about ocean pollution has been viewed 50 million times and inspired cleanup campaigns worldwide.", true_sentiment="positive", true_topic="culture", true_urgency="low"),

    # --- FINAL BATCH (balance) ---
    TextSnippet(text="The self-driving truck completed a 500-mile delivery route with zero human intervention.", true_sentiment="positive", true_topic="technology", true_urgency="low"),
    TextSnippet(text="Water contamination levels in the river have tripled since the factory opened upstream.", true_sentiment="negative", true_topic="science", true_urgency="high"),
    TextSnippet(text="The coalition government collapsed after the junior partner withdrew over policy disagreements.", true_sentiment="negative", true_topic="politics", true_urgency="medium"),
    TextSnippet(text="The graphic novel adaptation won the Palme d'Or, the first comic-based film to do so.", true_sentiment="positive", true_topic="culture", true_urgency="low"),
    TextSnippet(text="A 6.2 magnitude earthquake struck the coastal region; tsunami warnings have been issued.", true_sentiment="negative", true_topic="other", true_urgency="high"),
    TextSnippet(text="The open-source AI model matched proprietary performance at a fraction of the training cost.", true_sentiment="positive", true_topic="technology", true_urgency="low"),
    TextSnippet(text="New evidence suggests the ancient civilization had sophisticated astronomical knowledge previously unrecognized.", true_sentiment="positive", true_topic="science", true_urgency="low"),
    TextSnippet(text="The prime minister's approval rating is at 50%, unchanged from last quarter despite controversies.", true_sentiment="neutral", true_topic="politics", true_urgency="low"),
    TextSnippet(text="The jazz festival moved online permanently, losing the atmosphere but gaining a global audience.", true_sentiment="neutral", true_topic="culture", true_urgency="low"),
    TextSnippet(text="Supply chain disruptions are causing medication shortages at pharmacies across the country.", true_sentiment="negative", true_topic="other", true_urgency="high"),
]

assert len(DATASET) == 80, f"Expected 80 snippets, got {len(DATASET)}"


def get_batch(batch_size: int, seed: int | None = None) -> list[TextSnippet]:
    """Return a shuffled batch of snippets.

    Uses a seeded RNG so batches are reproducible per cycle but different
    across cycles.
    """
    rng = random.Random(seed)
    pool = list(DATASET)
    rng.shuffle(pool)
    return pool[:batch_size]


def get_partitioned_batches(
    batch_size: int, num_batches: int, seed: int = 42,
) -> list[list[TextSnippet]]:
    """Return non-overlapping batches for measuring generalization.

    If we need more snippets than the dataset has, batches will wrap
    with different orderings.
    """
    rng = random.Random(seed)
    pool = list(DATASET)
    rng.shuffle(pool)
    batches = []
    idx = 0
    for _ in range(num_batches):
        if idx + batch_size > len(pool):
            rng.shuffle(pool)
            idx = 0
        batches.append(pool[idx : idx + batch_size])
        idx += batch_size
    return batches
