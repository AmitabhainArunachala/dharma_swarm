# Cryptographic Audit Trails and Immutable Ledger Systems for Software Evolution

**Research Report**
**Date**: 2026-03-08
**Purpose**: Investigation of proven cryptographic audit trail systems for tamper-proof software evolution tracking in dharma_swarm
**Researcher**: Research Agent (dharma_swarm)

---

## Executive Summary

This report identifies three proven cryptographic audit trail systems suitable for software evolution tracking: **Sigstore** (keyless signing with transparency logs), **in-toto/SLSA** (supply chain integrity framework), and **Merkle tree-based systems** (tamper-evident logging). All three leverage cryptographic primitives to create verifiable, tamper-resistant records of software artifacts and development processes.

**Key Finding**: Sigstore emerges as the most mature solution with widespread adoption (NPM, PyPI, Maven, GitHub, Kubernetes), minimal performance overhead, and integration with existing development workflows. in-toto/SLSA provides comprehensive supply chain attestation but faces adoption challenges due to implementation complexity. Merkle trees offer the foundational cryptographic primitive used by both systems.

---

## 1. Top 3 Proven Audit Trail Systems

### 1.1 Sigstore (Keyless Signing with Transparency Logs)

**Status**: Production-ready, Linux Foundation project
**Adoption**: NPM, PyPI, Maven, GitHub, Homebrew, Kubernetes
**Components**: Cosign (signing CLI), Fulcio (CA), Rekor (transparency log)

#### How It Works

1. **Ephemeral Key Generation**: Client creates public/private key pair per signing event
2. **OIDC Identity Binding**: Certificate signing request includes verifiable OIDC identity token (email, service account, workflow info)
3. **Short-Lived Certificates**: Fulcio CA issues certificate bound to identity + public key (minutes to hours lifetime)
4. **Transparency Logging**: All signing events recorded in Rekor (append-only, tamper-resistant log)
5. **Keyless Verification**: Verifiers check signature against transparency log, not long-lived keys

**Cryptographic Primitives**:
- X.509 certificates with OIDC identity binding
- Certificate Transparency logs (distinct from Rekor)
- Merkle tree-based transparency log (Rekor)
- Ed25519 or ECDSA signatures

#### Adoption Statistics

- **Ecosystems**: NPM, PyPI, Maven, GitHub, Homebrew, Kubernetes
- **Git Integration**: Gitsign for keyless Git commit signing (GitHub, GitLab, Bitbucket support)
- **Container Signing**: Cosign widely adopted for OCI container image signing
- **Industry Traction**: Multiple CI/CD platforms (CircleCI, GitHub Actions, GitLab CI) support Sigstore natively

#### Tamper-Proof Guarantees

- **Certificate Transparency Log**: Tracks all issued certificates, allows verification after OIDC key rotation
- **Rekor Transparency Log**: Immutable record of all signing events
- **Post-Expiration Verification**: Commits verified via Rekor even after certificate expiration
- **Non-Repudiation**: OIDC identity binding prevents denial of authorship

### 1.2 in-toto / SLSA Framework (Supply Chain Integrity)

**Status**: SLSA v1.1 stable (2024), v1.2 RC1 released (2025)
**Adoption**: Part of OpenSSF, integrated with SLSA provenance
**Scope**: End-to-end supply chain security from source to deployment

#### How It Works

1. **Layout Definition**: Project owner defines supply chain steps and authorized functionaries
2. **Link Metadata**: Each step generates signed metadata (command, inputs, outputs, functionary identity)
3. **Final Product Verification**: End-user verifies complete chain of custody
4. **SLSA Provenance**: Attestations using in-toto format track build process (build platform, source repo, build command)

**SLSA Levels**:
- **Level 1**: Build process documented
- **Level 2**: Build integrity enforced, provenance generated, artifacts signed
- **Level 3**: Secure build environments (Tekton, Google Cloud Build), hardened provenance
- **Level 4**: Two-person review, hermetic builds

#### Adoption Statistics

- **Status**: "Adoption is not widespread" (2025 research)
- **Barriers**: Complex implementation, unclear communication (study of 1,523 SLSA issues in 233 GitHub repos)
- **Industry Examples**: Financial services (Level 2), SaaS providers (Level 3 with secure build environments)
- **Integration**: Part of NIST SSDF guidance, required for federal software procurement (until M-26-05 rescinded attestation requirement in Jan 2026)

#### Tamper-Proof Guarantees

- **Cryptographic Signatures**: Each link metadata file signed by functionary
- **Chain of Custody**: Complete provenance from source commit to deployed artifact
- **Attestation Framework**: Generic framework supporting SPDX, CycloneDX, SCAI, SLSA verification summaries
- **Build Provenance**: Immutable record of build inputs, platform, command

### 1.3 Merkle Tree-Based Audit Trails

**Status**: Foundational primitive used by Sigstore, Certificate Transparency, blockchain
**Adoption**: Google Certificate Transparency, Trillian (Google), Verifiable Data Structures
**Scope**: Tamper-evident append-only logs

#### How It Works

1. **Hash Chaining**: Each log entry hashed with previous entry
2. **Tree Construction**: Hashes organized in binary tree structure
3. **Root Hash**: Single hash representing entire log state
4. **Inclusion Proofs**: Logarithmic-size proof that entry exists in log
5. **Consistency Proofs**: Verify log only appended (not modified)

**Cryptographic Primitives**:
- SHA-256 or similar collision-resistant hash functions
- Binary Merkle tree construction
- Inclusion proof verification (O(log n) size)
- Consistency proof verification

#### Adoption Statistics

- **Google Certificate Transparency**: Monitors all publicly trusted TLS certificates
- **Trillian**: Google's verifiable data structures framework
- **Blockchain**: Bitcoin, Ethereum use Merkle trees for transaction verification
- **Timestamping**: RFC 3161 timestamping uses hash chains

#### Tamper-Proof Guarantees

- **Append-Only**: Any modification changes root hash
- **Efficient Verification**: O(log n) proof size for inclusion/consistency
- **Mathematical Detectability**: Tampering by anyone (including admins) is provably detectable
- **Anchoring**: Root hash anchored in hard-to-alter location (blockchain, newspaper, HSM)

---

## 2. Integration with Existing Development Workflows

### 2.1 Sigstore Integration

**Git Commit Signing (Gitsign)**:
```bash
# Install gitsign
brew install sigstore/tap/gitsign

# Configure git
git config --global commit.gpgsign true
git config --global tag.gpgsign true
git config --global gpg.x509.program gitsign
git config --global gpg.format x509

# Sign commits (automatic OIDC flow)
git commit -m "feat: add feature"
# Prompts for OIDC login (GitHub, Google, Microsoft)
# Signature stored in Rekor transparency log
```

**CI/CD Integration (GitHub Actions)**:
```yaml
- name: Install Cosign
  uses: sigstore/cosign-installer@v3

- name: Sign container image
  run: |
    cosign sign --yes $IMAGE_DIGEST
  env:
    COSIGN_EXPERIMENTAL: 1  # Keyless mode
```

**Verification**:
```bash
# Verify git commit
gitsign verify HEAD

# Verify container image
cosign verify $IMAGE_DIGEST \
  --certificate-identity=user@example.com \
  --certificate-oidc-issuer=https://github.com/login/oauth
```

### 2.2 in-toto/SLSA Integration

**Layout Definition** (`root.layout`):
```json
{
  "steps": [
    {
      "name": "code-review",
      "expected_materials": [["MATCH", "*.py", "WITH", "PRODUCTS", "FROM", "clone"]],
      "expected_products": [["CREATE", "*.py"]],
      "pubkeys": ["reviewer-key-id"],
      "threshold": 2
    }
  ],
  "inspect": [
    {
      "name": "verify-tests",
      "run": ["pytest", "tests/"]
    }
  ]
}
```

**Link Metadata Generation**:
```bash
# Generate link metadata for build step
in-toto-run --step-name build \
  --materials src/ \
  --products dist/ \
  --key build-key.pem \
  -- python setup.py build
```

**Final Verification**:
```bash
# Verify complete supply chain
in-toto-verify --layout root.layout \
  --layout-keys owner-key.pub \
  --link-dir .
```

### 2.3 Merkle Tree Integration

**Tamper-Proof Event Log**:
```python
import hashlib
import json

class MerkleLog:
    def __init__(self):
        self.entries = []
        self.tree = []

    def append(self, data):
        # Hash new entry with previous root
        prev_root = self.tree[-1] if self.tree else b'\x00' * 32
        entry_hash = hashlib.sha256(
            prev_root + json.dumps(data).encode()
        ).digest()

        self.entries.append(data)
        self.tree.append(entry_hash)
        return entry_hash.hex()

    def verify_inclusion(self, index, data):
        # Reconstruct hash chain
        prev_root = self.tree[index - 1] if index > 0 else b'\x00' * 32
        expected = hashlib.sha256(
            prev_root + json.dumps(data).encode()
        ).digest()
        return expected == self.tree[index]
```

---

## 3. Performance Overhead

### 3.1 Sigstore Performance

**Signing Overhead**:
- **OIDC Authentication**: 1-3 seconds (one-time per session)
- **Certificate Issuance**: <100ms (Fulcio)
- **Signature Generation**: <50ms (Ed25519)
- **Rekor Upload**: <200ms (transparency log)
- **Total First-Commit Overhead**: ~2-4 seconds
- **Subsequent Commits**: <300ms (cached OIDC token)

**Storage Overhead**:
- **Signature Size**: ~500 bytes (X.509 certificate + signature)
- **Transparency Log Entry**: ~1 KB per signing event
- **Git Repo Growth**: Negligible (<0.01% for typical repos)

**Verification Overhead**:
- **Certificate Validation**: <50ms
- **Rekor Proof Fetch**: <100ms
- **Signature Verification**: <10ms
- **Total**: <200ms per verification

**Benchmark Source**: Based on Sigstore community discussions and typical Ed25519 performance (64K sigs/sec on modern CPU).

### 3.2 in-toto/SLSA Performance

**Link Metadata Generation**:
- **Material Hashing**: O(n) in file count, ~1ms per file for SHA-256
- **Signature Generation**: <50ms (RSA-2048 or Ed25519)
- **Typical Build Step**: 100-500ms overhead for 100-file project

**Final Verification**:
- **Layout Verification**: <10ms (parse + validate)
- **Link Verification**: O(steps), ~50ms per step
- **Typical Pipeline**: 200-1000ms for 5-10 step chain

**Storage Overhead**:
- **Link Metadata**: ~5-50 KB per step (depends on material/product count)
- **Layout File**: 1-10 KB
- **Typical Project**: <1 MB total metadata

**Benchmark Source**: Estimated from in-toto Python implementation, typical crypto operation costs.

### 3.3 Merkle Tree Performance

**Append Operation**:
- **Hash Computation**: <1ms (SHA-256 of ~1 KB entry)
- **Tree Update**: O(log n) node updates, typically <5ms for 1M entries
- **Total**: <10ms per append

**Inclusion Proof**:
- **Proof Size**: O(log n), ~32 bytes × log₂(n) = 640 bytes for 1M entries
- **Verification Time**: <1ms (hash log₂(n) nodes)

**Storage Overhead**:
- **Hash Size**: 32 bytes per entry (SHA-256)
- **Tree Nodes**: 2n-1 nodes for n entries = ~64 KB for 1K entries
- **Anchoring**: Additional overhead if anchored to blockchain

**Benchmark Source**: Standard Merkle tree performance, validated in Trillian and Certificate Transparency implementations.

---

## 4. Case Studies: Audit Trails Preventing/Detecting Tampering

### 4.1 SolarWinds Attack (What Could Have Prevented It)

**Attack Vector**: Build process infiltration, trojanized DLL with valid digital signature

**How Audit Trails Would Help**:
1. **SLSA Build Provenance**: Would have flagged anomalous build environment
2. **Binary Attestation**: Sandbox disassembly would detect 1096-byte static array staging process hashes
3. **Transparency Log**: Build-time signing with Rekor would create immutable record of attacker's identity
4. **Two-Person Review (SLSA L4)**: Second reviewer would scrutinize OrionImprovementBusinessLayer class

**Actual Detection**: Post-breach forensics revealed tampering, but no real-time prevention

**Source**: OPSWAT analysis of SolarWinds prevention strategies

### 4.2 npm Malicious Package Detection

**Attack Vector**: Compromised maintainer accounts, malicious installation scripts

**How Audit Trails Helped**:
1. **Package Metadata Analysis**: Study of 1.63M npm packages using 6 indicators of compromise
2. **Installation Script Detection**: Identified 10+ malicious packages via script analysis
3. **Maintainer Domain Expiration**: Flagged packages with expired maintainer domains
4. **Provenance Tracking**: Linked malicious packages to compromised accounts

**Detection Rate**: 10+ malicious packages identified from 1.63M corpus

**Limitation**: Post-publication detection, not real-time prevention

**Source**: "Backstabber's Knife Collection" research (PMC)

### 4.3 GitHub Commit Signature Verification at Scale

**Attack Vector**: Compromised developer accounts, unauthorized code changes

**How Audit Trails Prevent Tampering**:
1. **Persistent Verification**: GitHub stores verification record alongside commit
2. **Key Rotation Resilience**: Verification persists even after signing key rotation/revocation
3. **Organization Departures**: Signatures remain verified after contributors leave
4. **Transparency Log**: Gitsign + Rekor creates append-only audit trail

**Real-World Impact**:
- **Non-Repudiation**: Developer cannot deny authorship of signed commit
- **Timeline Integrity**: Commit timestamps verified via certificate issuance time
- **Identity Binding**: OIDC identity prevents account hijacking masquerading

**Adoption**: Major projects (Kubernetes, Tekton, CNCF projects) require signed commits

**Source**: GitHub documentation, Sigstore Gitsign case studies

### 4.4 Google Binary Authorization (Container Deployment Prevention)

**Attack Vector**: Compromised container images, unauthorized deployments

**How Audit Trails Prevent Tampering**:
1. **Attestation Requirement**: Only images with valid attestations can deploy
2. **Multi-Attestor Policies**: Require attestations from multiple signers (dev, security, compliance)
3. **Digest-Based Verification**: Attestations tied to image digest (content-addressable)
4. **Deploy-Time Enforcement**: Binary Authorization enforcer blocks unattested images

**Real-World Impact**:
- **Zero Unattested Deployments**: Policy enforcement at GKE control plane
- **Compliance Auditing**: All deployment attempts logged with attestation status
- **Break-Glass Mechanism**: Override requires explicit exception with audit trail

**Adoption**: Google internal infrastructure, GKE customers (financial services, healthcare)

**Source**: Google Cloud Binary Authorization documentation

---

## 5. Recommendations for dharma_swarm Proof Chain

### 5.1 Immediate Implementation (Weeks 1-2)

**Goal**: Establish cryptographic audit trail for code evolution

**Action Items**:
1. **Git Commit Signing with Gitsign**
   - Install gitsign for all developers
   - Configure global git settings for automatic signing
   - Enforce signed commits via branch protection (GitHub)
   - **Rationale**: Zero-key-management overhead, immediate transparency log integration

2. **Merkle Log for Evolution Archive**
   - Extend `archive.py` to include Merkle tree root in each archive entry
   - Store hash chain in `.dharma/evolution_merkle.json`
   - Add `dgc evolve verify-chain` command
   - **Rationale**: Tamper-evident evolution history, lightweight implementation

3. **Provenance Metadata in Evolution Records**
   - Add fields: `git_commit_sha`, `rekor_log_index`, `signer_identity`
   - Store in evolution archive JSONL
   - **Rationale**: Link code changes to evolution decisions

**Implementation Example**:
```python
# dharma_swarm/archive.py
import hashlib
import json

class EvolutionArchive:
    def __init__(self):
        self.merkle_log = MerkleLog()

    def archive_proposal(self, proposal, fitness, git_commit):
        # Standard archival
        entry = {
            "timestamp": now(),
            "proposal": proposal,
            "fitness": fitness,
            "git_commit_sha": git_commit,
            "rekor_index": get_rekor_index(git_commit),
            "signer": get_oidc_identity()
        }

        # Merkle log entry
        merkle_root = self.merkle_log.append(entry)
        entry["merkle_root"] = merkle_root

        self.write_jsonl(entry)
        return merkle_root
```

### 5.2 Medium-Term Integration (Weeks 3-6)

**Goal**: Full supply chain attestation for evolved code

**Action Items**:
1. **SLSA Provenance for Darwin Engine**
   - Generate provenance attestation when evolution proposal accepted
   - Include: original code, proposed diff, fitness evaluation, test results
   - Sign with gitsign, upload to Rekor
   - **Rationale**: End-to-end auditability of self-modification

2. **Container Signing for TUI/CLI Distributions**
   - Sign `dharma_swarm` Docker images with Cosign
   - Store signatures in OCI registry
   - Verify at startup (optional flag for development)
   - **Rationale**: Deployment integrity for production environments

3. **Automated Verification in CI/CD**
   - Add GitHub Actions workflow to verify all commits signed
   - Fail PR if evolution archive Merkle chain invalid
   - Generate weekly audit report
   - **Rationale**: Continuous verification, prevent chain breaks

### 5.3 Long-Term Vision (Months 2-3)

**Goal**: Self-sovereign evolution with public auditability

**Action Items**:
1. **Public Evolution Transparency Log**
   - Mirror evolution archive to public append-only log (Rekor or custom)
   - Publish weekly Merkle root to IPFS or blockchain
   - Provide web UI for community auditing
   - **Rationale**: Aligns with Jagat Kalyan (universal welfare) telos

2. **Multi-Party Evolution Attestation**
   - Require 2-of-3 signatures for high-impact changes (SLSA L4 style)
   - Roles: code, safety (telos gates), test (behavioral metrics)
   - Implement threshold signature scheme
   - **Rationale**: Distributed governance, prevent single-point manipulation

3. **Formal Verification Integration**
   - Store formal proofs of safety properties in evolution archive
   - Link to AHIMSA, SATYA gate verdicts
   - Merkle-ize proof trees
   - **Rationale**: Cryptographic proof of alignment with dharmic principles

### 5.4 Specific Technical Recommendations

**Technology Stack**:
- **Primary**: Sigstore (Cosign for artifacts, Gitsign for commits)
- **Secondary**: in-toto attestations for complex workflows
- **Foundation**: Merkle trees for local tamper-evident logs

**Storage Architecture**:
```
~/.dharma/
├── evolution_archive.jsonl       # Standard archive
├── evolution_merkle.json         # Hash chain
├── attestations/
│   ├── proposals/                # in-toto link metadata
│   ├── evaluations/              # Fitness assessment attestations
│   └── gates/                    # Telos gate verdicts
└── rekor_cache/                  # Cached transparency log proofs
```

**Verification Commands**:
```bash
# Verify evolution chain integrity
dgc evolve verify-chain

# Verify specific proposal
dgc evolve verify-proposal <proposal-id>

# Audit evolution history (full transparency)
dgc evolve audit --from <date> --to <date>

# Verify git commit in Rekor
gitsign verify <commit-sha>
```

**Performance Budget**:
- **Signing Overhead**: <500ms per evolution proposal (acceptable for infrequent events)
- **Verification Overhead**: <1s for full chain verification (acceptable for CI/CD)
- **Storage Growth**: <10 MB/year for typical evolution rate (100 proposals/year)

---

## 6. Comparative Analysis

| Criteria | Sigstore | in-toto/SLSA | Merkle Trees |
|----------|----------|--------------|--------------|
| **Maturity** | Production (2021+) | SLSA v1.1 stable | Foundational primitive |
| **Adoption** | High (NPM, PyPI, K8s) | Low (complex) | Very high (CT, blockchain) |
| **Keyless** | Yes (OIDC) | No (long-lived keys) | N/A (hash-based) |
| **Transparency** | Rekor public log | Optional | Depends on implementation |
| **Integration Ease** | Excellent | Moderate | Varies |
| **Performance** | <500ms signing | ~500ms/step | <10ms append |
| **Storage Overhead** | ~1 KB/event | ~10 KB/step | ~32 bytes/entry |
| **Tamper Detection** | Cryptographic | Cryptographic | Cryptographic |
| **Non-Repudiation** | Strong (OIDC) | Strong (signatures) | Weak (no identity) |
| **Supply Chain Scope** | Artifacts only | End-to-end | Logs only |
| **Developer UX** | Excellent | Poor | N/A (infrastructure) |

**Winner for dharma_swarm**: **Sigstore** for primary audit trail, **Merkle trees** for local evolution chain, **in-toto** for future multi-party workflows.

---

## 7. Key Insights from Research

### 7.1 Keyless Signing Is the Future

Traditional code signing requires managing long-lived private keys (storage, rotation, revocation). Sigstore's keyless approach:
- **Eliminates Key Management**: No private keys to protect
- **OIDC Identity Binding**: Leverages existing identity providers (GitHub, Google)
- **Short-Lived Certificates**: Minutes-to-hours lifetime reduces compromise window
- **Transparency Log Verification**: Public auditability without key distribution

**Implication for dharma_swarm**: Adopt gitsign immediately. Zero operational overhead, maximum security.

### 7.2 Transparency Logs Enable Post-Hoc Verification

Certificate Transparency revolutionized TLS by creating append-only logs of all issued certificates. Same principle applies to code signing:
- **Rekor**: Public log of all Sigstore signing events
- **Verification Without Signer**: Anyone can verify signature via log lookup
- **Temporal Proof**: Log entry timestamp proves signing time
- **Key Rotation Resilience**: Verification works even after OIDC keys rotated

**Implication for dharma_swarm**: Evolution archive entries can be verified indefinitely, even if developers leave or keys lost.

### 7.3 SLSA Adoption Lags Due to Complexity

Despite strong theoretical foundation, SLSA faces adoption barriers:
- **Implementation Complexity**: Multi-step attestation workflows hard to implement
- **Unclear Communication**: Specification dense, tooling immature
- **Ecosystem Fragmentation**: Different build systems require custom integrations

**Implication for dharma_swarm**: Start with Sigstore (simple), add SLSA incrementally as workflows mature.

### 7.4 Merkle Trees Are Universal Building Block

Every modern audit trail system uses Merkle trees:
- **Certificate Transparency**: Merkle tree of certificates
- **Rekor**: Merkle tree of signing events
- **Blockchain**: Merkle tree of transactions
- **Git**: Merkle DAG of commits (conceptually similar)

**Implication for dharma_swarm**: Adding Merkle tree to evolution archive is low-hanging fruit with high security value.

### 7.5 Federal Requirements Driving Adoption

NIST SSDF, OMB M-22-18 (now rescinded), and CISA SBOM requirements created compliance pressure:
- **2026 Turning Point**: Federal procurement requires attestations
- **SBOM Mandatory**: Software bill of materials expected in enterprise sales
- **Audit Trail Documentation**: NIST SP 800-53 emphasizes tamper-evident logging

**Implication for dharma_swarm**: Industry moving toward mandatory provenance. Early adoption = competitive advantage for research credibility.

---

## 8. Glossary

- **Attestation**: Cryptographically signed statement about software artifact (e.g., "I built this binary from commit X")
- **Certificate Transparency (CT)**: Public log of all TLS certificates, enables detection of mis-issued certificates
- **Cosign**: Sigstore tool for signing and verifying container images
- **Fulcio**: Sigstore certificate authority, issues short-lived certificates based on OIDC identity
- **Gitsign**: Sigstore tool for signing Git commits with keyless signatures
- **in-toto**: Framework for securing software supply chain via cryptographic link metadata
- **Merkle Tree**: Binary tree of cryptographic hashes, enables efficient proof of inclusion/consistency
- **OIDC (OpenID Connect)**: Identity layer on OAuth 2.0, used by Sigstore for identity binding
- **Provenance**: Record of how software artifact was created (source, build platform, dependencies)
- **Rekor**: Sigstore transparency log, append-only ledger of signing events
- **SBOM (Software Bill of Materials)**: Inventory of software components and dependencies
- **SLSA**: Supply-chain Levels for Software Artifacts, framework defining 4 levels of supply chain security
- **Transparency Log**: Append-only cryptographic log enabling public auditability

---

## 9. References and Sources

### Sigstore
- [Sigstore Overview](https://docs.sigstore.dev/about/overview/)
- [Keyless Signing with Sigstore and CI/MON - Cycode](https://cycode.com/blog/securing-artifacts-keyless-signing-with-sigstore-and-ci-mon/)
- [Use Sigstore for keyless signing and verification - GitLab](https://docs.gitlab.com/ci/yaml/signing_examples/)
- [Scaling Up Supply Chain Security with Sigstore - OpenSSF](https://openssf.org/blog/2024/02/16/scaling-up-supply-chain-security-implementing-sigstore-for-seamless-container-image-signing/)
- [GitHub - sigstore/cosign](https://github.com/sigstore/cosign)
- [How to Implement Supply Chain Security with Sigstore](https://oneuptime.com/blog/post/2026-01-25-sigstore-supply-chain-security/view)

### in-toto and SLSA
- [in-toto](https://in-toto.io/)
- [SLSA • in-toto and SLSA](https://slsa.dev/blog/2023/05/in-toto-and-slsa)
- [What is the SLSA Framework? - JFrog](https://jfrog.com/learn/grc/slsa-framework/)
- [SLSA Framework: What is It and How to Gain Visibility - Legit Security](https://www.legitsecurity.com/blog/slsa-provenance-blog-series-part-2-deeper-dive-into-slsa-provenance)
- [GitHub - in-toto/in-toto](https://github.com/in-toto/in-toto)
- [SLSA • Provenance](https://slsa.dev/spec/v0.1/provenance)
- [Analyzing Challenges in Deployment of SLSA Framework - arXiv](https://arxiv.org/abs/2409.05014)
- [SLSA Framework Guide 2026](https://www.practical-devsecops.com/slsa-framework-guide-software-supply-chain-security/)

### Software Bill of Materials (SBOM)
- [Software Bill of Materials (SBOM) - CISA](https://www.cisa.gov/sbom)
- [SBOMs in 2026: Some Love, Some Hate, Much Ambivalence - Dark Reading](https://www.darkreading.com/application-security/sboms-in-2026-some-love-some-hate-much-ambivalence)
- [What Is a Software Bill of Materials (SBOM)? - IBM](https://www.ibm.com/think/topics/sbom)
- [SBOM: Software Bill of Materials Guide - Calmops](https://calmops.com/security/sbom-software-bill-materials/)
- [SBOMs: The Foundation of Software Supply Chain Security - Wiz](https://www.wiz.io/academy/application-security/software-bill-of-material-sbom)

### Merkle Trees and Tamper-Proof Logging
- [A Tamperproof Logging Implementation - Pangea](https://pangea.cloud/blog/a-tamperproof-logging-implementation)
- [Efficient Data Structures for Tamper-Evident Logging - USENIX](https://static.usenix.org/event/sec09/tech/full_papers/crosby.pdf)
- [Audit trails and tamper evidence - Scaling Strategies - Sachith Dassanayake](https://www.sachith.co.uk/audit-trails-and-tamper-evidence-scaling-strategies-practical-guide-feb-22-2026/)
- [Hash, Print, Anchor: Securing Logs with Merkle Trees - Medium](https://medium.com/@vanabharathiraja/%EF%B8%8F-building-a-tamper-proof-event-logging-system-e71dfbc3c58a)
- [Verifiable Data Structures - Trillian](https://transparency.dev/verifiable-data-structures/)
- [Building Tamper-Proof Audit Trails - DEV Community](https://dev.to/veritaschain/building-tamper-proof-audit-trails-what-three-2025-trading-disasters-teach-us-about-cryptographic-378g)

### Git Commit Signing
- [Using Gitsign for Keyless Git Commit Signing - Ken Muse](https://www.kenmuse.com/blog/using-gitsign-for-keyless-git-commit-signing/)
- [Signed Git commits with Sigstore, Gitsign and OIDC - Buildkite](https://buildkite.com/resources/blog/securing-your-software-supply-chain-signed-git-commits-with-oidc-and-sigstore/)
- [Keyless Git commit signing with Gitsign and GitHub Actions - Chainguard](https://www.chainguard.dev/unchained/keyless-git-commit-signing-with-gitsign-and-github-actions)
- [About commit signature verification - GitHub](https://docs.github.com/en/authentication/managing-commit-signature-verification/about-commit-signature-verification)
- [Inspecting Gitsign Commit Signatures - Sigstore](https://docs.sigstore.dev/cosign/verifying/inspecting/)

### NIST and Federal Standards
- [NIST compliance in 2026: A complete implementation guide - UpGuard](https://www.upguard.com/blog/nist-compliance)
- [Supply Chain Security Standards: Aligning with NIST and ISO - DoHost](https://dohost.us/index.php/2026/02/16/supply-chain-security-standards-aligning-with-nist-and-iso-for-your-partner-ecosystem/)
- [What the 2026 State of the Software Supply Chain Report Reveals - Sonatype](https://www.sonatype.com/blog/what-the-2026-state-of-the-software-supply-chain-report-reveals-about-regulation)
- [Software Supply Chain Security Report 2026 - ReversingLabs](https://www.reversinglabs.com/blog/sscs-report-2026-guidance-timeline)
- [OMB Rescinds Secure Software Attestation Requirement - Inside Government Contracts](https://www.insidegovernmentcontracts.com/2026/02/omb-rescinds-the-common-form-secure-software-attestation-requirement/)
- [NIST Guide: Protecting Against Supply Chain Attacks - Scrut](https://www.scrut.io/post/nist-recommendations-software-supply-chain-attacks)
- [Cybersecurity Supply Chain Risk Management - NIST CSRC](https://csrc.nist.gov/Projects/cyber-supply-chain-risk-management/publications)

### Google Binary Authorization
- [Attestations overview - Binary Authorization - Google Cloud](https://docs.cloud.google.com/binary-authorization/docs/attestations)
- [Binary Authorization overview - Google Cloud](https://docs.cloud.google.com/binary-authorization/docs/overview)
- [Using Binary Authorization to boost supply chain security - Google Cloud Blog](https://cloud.google.com/transform/how-google-does-it-using-binary-authorization-to-boost-supply-chain-security)
- [Create attestations - Binary Authorization - Google Cloud](https://cloud.google.com/binary-authorization/docs/making-attestations)

### Case Studies and Attack Prevention
- [Understanding Supply Chain Attack Tactics With Case Study - Brandefense](https://brandefense.io/blog/understanding-supply-chain-attack-tactics-with-case-study/)
- [Tampering Detection AI Engine - Myrror Security](https://myrror.security/tampering-detection-ai-engine-how-to-prevent-the-next-software-supply-chain-attack/)
- [How the SolarWinds Supply Chain Attack Could Have Been Prevented - OPSWAT](https://www.opswat.com/blog/how-the-solarwinds-supply-chain-attack-could-have-been-prevented-using-metadefender-sandbox)
- [Backstabber's Knife Collection: Review of Open Source Software Supply Chain Attacks - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC7338168/)

---

## 10. Appendix: Quick Start Guide for dharma_swarm

### A. Install Gitsign (5 minutes)

```bash
# macOS
brew install sigstore/tap/gitsign

# Configure git globally
git config --global commit.gpgsign true
git config --global tag.gpgsign true
git config --global gpg.x509.program gitsign
git config --global gpg.format x509

# Test with a commit
cd ~/dharma_swarm
git commit -m "test: verify gitsign setup"
# Follow OIDC login prompt (GitHub)
```

### B. Add Merkle Log to Evolution Archive (30 minutes)

```python
# dharma_swarm/merkle_log.py
import hashlib
import json
from typing import Any, List, Tuple

class MerkleLog:
    """Tamper-evident append-only log using hash chaining."""

    def __init__(self, log_file: str = "~/.dharma/evolution_merkle.json"):
        self.log_file = Path(log_file).expanduser()
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        self.entries: List[bytes] = []
        self._load()

    def append(self, data: dict) -> str:
        """Append entry and return Merkle root."""
        prev_root = self.entries[-1] if self.entries else b'\x00' * 32
        entry_bytes = json.dumps(data, sort_keys=True).encode()
        entry_hash = hashlib.sha256(prev_root + entry_bytes).digest()

        self.entries.append(entry_hash)
        self._save()
        return entry_hash.hex()

    def verify_chain(self) -> Tuple[bool, int]:
        """Verify entire chain integrity. Returns (valid, last_valid_index)."""
        # Implementation: recompute all hashes, compare with stored
        pass

    def _load(self):
        if self.log_file.exists():
            with open(self.log_file) as f:
                data = json.load(f)
                self.entries = [bytes.fromhex(h) for h in data["hashes"]]

    def _save(self):
        with open(self.log_file, 'w') as f:
            json.dump({
                "hashes": [h.hex() for h in self.entries],
                "version": 1
            }, f, indent=2)
```

### C. Integrate with Evolution Archive

```python
# dharma_swarm/archive.py (add to existing class)
from .merkle_log import MerkleLog

class EvolutionArchive:
    def __init__(self, archive_path: str):
        self.archive_path = archive_path
        self.merkle = MerkleLog()  # Add this

    def archive_proposal(self, proposal: Proposal, fitness: float):
        # Existing archival logic
        entry = {
            "timestamp": datetime.now().isoformat(),
            "proposal": proposal.dict(),
            "fitness": fitness,
            # Add provenance
            "git_commit": get_current_commit_sha(),
            "signer": get_git_user_email(),
        }

        # Add to Merkle log
        merkle_root = self.merkle.append(entry)
        entry["merkle_root"] = merkle_root

        # Write to JSONL
        with open(self.archive_path, 'a') as f:
            f.write(json.dumps(entry) + '\n')

        return merkle_root
```

### D. Add Verification Command

```python
# dharma_swarm/cli.py (add command)
@app.command()
def verify_chain():
    """Verify evolution archive Merkle chain integrity."""
    archive = EvolutionArchive("~/.dharma/evolution_archive.jsonl")
    valid, last_index = archive.merkle.verify_chain()

    if valid:
        console.print(f"[green]✓[/green] Chain valid ({len(archive.merkle.entries)} entries)")
    else:
        console.print(f"[red]✗[/red] Chain broken at entry {last_index}")
        raise SystemExit(1)
```

---

**End of Report**

**Next Steps for dharma_swarm**:
1. Install gitsign and configure globally (today)
2. Implement Merkle log for evolution archive (this weekend)
3. Add `dgc evolve verify-chain` command (next week)
4. Research SLSA integration for multi-step workflows (month 2)
5. Publish evolution transparency log (month 3, aligns with COLM 2026 deadline)

**Alignment with Telos**: Cryptographic audit trails serve Jagat Kalyan by making AI evolution publicly auditable, tamper-resistant, and aligned with dharmic principles (SATYA truth, AHIMSA non-harm). The transparency log becomes living proof of alignment.
