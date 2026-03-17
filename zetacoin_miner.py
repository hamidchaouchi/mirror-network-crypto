"""
ZetaCoin (ZTC) — ZetaPoW-56 Miner
Based on the Mirror Network mathematical framework
H. Chaouchi, Algeria, March 2026
Research: zenodo.org/records/19060261
"""

import hashlib
import time
import json
import struct
import random
from mpmath import mp, zeta, mpc, re, im

# ── Precision ────────────────────────────────────────────
mp.dps = 20  # 20 decimal places

# ── Mirror Network Constants ─────────────────────────────
WORLDS    = [1, 7, 11, 13, 17, 19, 23, 29]   # (Z/30Z)*
K_VALS    = [1, 2, 5, 10, 20, 50, 100]        # universes
BASE_T    = [
    14.134725141734694, 21.022039638771555,
    25.010857580145688, 30.424876125859513,
    32.935061587739190, 37.586178158825671,
    40.918719012147495
]

# ── ZetaPoW-56 Core ──────────────────────────────────────

def zeta_world(r, k, t):
    """Evaluate partial zeta at world r, universe k, imaginary part t"""
    s = mpc(0.5, t)
    total = mpc(0, 0)
    for n in range(r, r + 30 * k + 1, 30):
        total += mpc(1, 0) / (n ** s)
    return total

def derive_56_hashes(t_matrix):
    """Compute 56 SHA-256 hashes from the t-matrix"""
    hashes = []
    for i, k in enumerate(K_VALS):
        for j, r in enumerate(WORLDS):
            t = t_matrix[i][j]
            z = zeta_world(r, k, t)
            raw = f"{float(re(z)):.14f}|{float(im(z)):.14f}|k={k}|r={r}"
            h = hashlib.sha256(raw.encode()).hexdigest()
            hashes.append(h)
    return hashes

def session_key_from_56(hashes):
    """XOR all 56 hashes into a single 256-bit session key"""
    key = bytearray(32)
    for h in hashes:
        hb = bytes.fromhex(h)
        for b in range(32):
            key[b] ^= hb[b]
    return key.hex()

def compute_block_hash(session_key, block_header, nonce):
    """Final block hash: SHA-256(session_key | header | nonce)"""
    data = bytes.fromhex(session_key) + block_header.encode() + struct.pack('<Q', nonce)
    return hashlib.sha256(data).hexdigest()

def hash_meets_target(block_hash, difficulty):
    """Check if hash meets the difficulty target (leading zeros)"""
    return block_hash.startswith('0' * difficulty)

# ── Default T-Matrix ─────────────────────────────────────

def default_t_matrix():
    return [
        [round(BASE_T[i] + j * 0.001, 12) for j in range(8)]
        for i in range(7)
    ]

# ── Block Structure ──────────────────────────────────────

def make_block_header(index, prev_hash, timestamp, merkle_root):
    return f"{index}|{prev_hash}|{timestamp}|{merkle_root}"

# ── Miner ────────────────────────────────────────────────

def mine_block(index, prev_hash, transactions, difficulty=4, t_matrix=None):
    """
    Mine a ZetaCoin block using ZetaPoW-56.
    Returns the mined block dict or None on failure.
    """
    if t_matrix is None:
        t_matrix = default_t_matrix()

    print(f"\n{'='*55}")
    print(f"  ZetaCoin Miner — ZetaPoW-56")
    print(f"  Block #{index}  |  Difficulty: {difficulty}")
    print(f"{'='*55}")

    # Step 1 — Compute 56 zeta hashes
    print("\n[1/4] Computing 56 zeta layers...")
    t0 = time.time()
    hashes = derive_56_hashes(t_matrix)
    session_key = session_key_from_56(hashes)
    zeta_time = time.time() - t0
    print(f"      Session key : {session_key[:24]}...")
    print(f"      Time        : {zeta_time:.2f}s")

    # Step 2 — Build block header
    timestamp   = int(time.time())
    merkle_root = hashlib.sha256(json.dumps(transactions).encode()).hexdigest()
    header      = make_block_header(index, prev_hash, timestamp, merkle_root)
    print(f"\n[2/4] Block header built")
    print(f"      Merkle root : {merkle_root[:24]}...")

    # Step 3 — Mining loop
    print(f"\n[3/4] Mining (target: {difficulty} leading zeros)...")
    nonce        = 0
    start        = time.time()
    found        = False

    while nonce < 10_000_000:
        block_hash = compute_block_hash(session_key, header, nonce)
        if hash_meets_target(block_hash, difficulty):
            found = True
            break
        nonce += 1
        if nonce % 5000 == 0:
            elapsed = time.time() - start
            rate    = nonce / elapsed if elapsed > 0 else 0
            print(f"      Nonce {nonce:>9,}  |  {rate:>8,.0f} H/s  |  {elapsed:.1f}s", end='\r')

    elapsed = time.time() - start

    if not found:
        print(f"\n      [!] No solution found after 10M nonces")
        return None

    # Step 4 — Block found!
    print(f"\n\n[4/4] BLOCK FOUND! ✓")
    print(f"{'='*55}")
    print(f"  Block hash  : {block_hash}")
    print(f"  Nonce       : {nonce:,}")
    print(f"  Mining time : {elapsed:.2f}s")
    print(f"  Hash rate   : {nonce/elapsed:,.0f} H/s")
    print(f"  Reward      : 50 ZTC")
    print(f"{'='*55}\n")

    return {
        "index"       : index,
        "timestamp"   : timestamp,
        "transactions": transactions,
        "prev_hash"   : prev_hash,
        "merkle_root" : merkle_root,
        "session_key" : session_key,
        "nonce"       : nonce,
        "hash"        : block_hash,
        "difficulty"  : difficulty,
        "zeta_time_s" : round(zeta_time, 3),
        "mine_time_s" : round(elapsed, 3),
        "reward_ztc"  : 50,
    }

# ── Simple Blockchain ────────────────────────────────────

class ZetaChain:
    def __init__(self):
        self.chain      = []
        self.difficulty = 3   # start easy for testing
        self._create_genesis()

    def _create_genesis(self):
        genesis = {
            "index"       : 0,
            "timestamp"   : int(time.time()),
            "transactions": [{"from": "network", "to": "genesis", "amount": 0}],
            "prev_hash"   : "0" * 64,
            "merkle_root" : "0" * 64,
            "session_key" : "0" * 64,
            "nonce"       : 0,
            "hash"        : hashlib.sha256(b"ZetaCoin Genesis Block").hexdigest(),
            "difficulty"  : 0,
            "reward_ztc"  : 0,
        }
        self.chain.append(genesis)
        print(f"Genesis block created: {genesis['hash'][:24]}...")

    def add_block(self, transactions, wallet_address, t_matrix=None):
        prev   = self.chain[-1]
        index  = len(self.chain)
        txns   = transactions + [{"from": "network", "to": wallet_address, "amount": 50}]
        block  = mine_block(index, prev["hash"], txns, self.difficulty, t_matrix)
        if block:
            self.chain.append(block)
            return block
        return None

    def is_valid(self):
        for i in range(1, len(self.chain)):
            curr = self.chain[i]
            prev = self.chain[i-1]
            if curr["prev_hash"] != prev["hash"]:
                return False
        return True

    def print_chain(self):
        print(f"\n{'='*55}")
        print(f"  ZetaChain — {len(self.chain)} blocks")
        print(f"{'='*55}")
        for b in self.chain:
            print(f"  #{b['index']:>3}  hash={b['hash'][:20]}...  nonce={b.get('nonce',0):>8,}  reward={b.get('reward_ztc',0)} ZTC")
        print(f"{'='*55}")
        print(f"  Chain valid: {self.is_valid()}")
        print()

# ── Main ─────────────────────────────────────────────────

if __name__ == "__main__":
    print("""
╔═══════════════════════════════════════════════════════╗
║          ZetaCoin (ZTC) — ZetaPoW-56 Miner            ║
║   Every hash solves real mathematics                  ║
║   github.com/hamidchaouchi/mirror-network-crypto      ║
╚═══════════════════════════════════════════════════════╝
""")

    # Your wallet address
    MY_WALLET = "ztc1_hamidchaouchi_algeria_2026"

    # Create blockchain
    chain = ZetaChain()

    # Mine 2 blocks
    for i in range(2):
        transactions = [
            {"from": MY_WALLET, "to": "receiver_1", "amount": 1.0},
        ]
        block = chain.add_block(transactions, MY_WALLET)
        if block:
            print(f"Block #{block['index']} added to chain!")

    # Print final chain
    chain.print_chain()

    # Save chain to JSON
    with open("/home/claude/zetachain.json", "w") as f:
        json.dump(chain.chain, f, indent=2)
    print("Chain saved to zetachain.json")
