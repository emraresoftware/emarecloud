"""
EmareCloud — Akıllı Kontrat ABI ve Adresleri
EmareToken ekosistemindeki kontratlarla iletişim için gerekli ABI tanımları.

NOT: ABI'ler kontratlar deploy edildikten sonra artifacts/ klasöründen alınır.
     Burada sadece entegrasyon için gerekli minimal ABI'ler tanımlıdır.
"""

# ==================== EMARE TOKEN (ERC20) ABI ====================
EMARE_TOKEN_ABI = [
    # Okuma fonksiyonları
    {"inputs": [], "name": "name", "outputs": [{"type": "string"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "symbol", "outputs": [{"type": "string"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "decimals", "outputs": [{"type": "uint8"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "totalSupply", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "MAX_SUPPLY", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"name": "account", "type": "address"}], "name": "balanceOf",
     "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"name": "owner", "type": "address"}, {"name": "spender", "type": "address"}],
     "name": "allowance", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"name": "", "type": "address"}], "name": "minters",
     "outputs": [{"type": "bool"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "paused", "outputs": [{"type": "bool"}], "stateMutability": "view", "type": "function"},
    # Yazma fonksiyonları
    {"inputs": [{"name": "to", "type": "address"}, {"name": "amount", "type": "uint256"}],
     "name": "transfer", "outputs": [{"type": "bool"}], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [{"name": "spender", "type": "address"}, {"name": "amount", "type": "uint256"}],
     "name": "approve", "outputs": [{"type": "bool"}], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [{"name": "from", "type": "address"}, {"name": "to", "type": "address"}, {"name": "amount", "type": "uint256"}],
     "name": "transferFrom", "outputs": [{"type": "bool"}], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [{"name": "amount", "type": "uint256"}],
     "name": "burn", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    # Events
    {"anonymous": False, "inputs": [
        {"indexed": True, "name": "from", "type": "address"},
        {"indexed": True, "name": "to", "type": "address"},
        {"indexed": False, "name": "value", "type": "uint256"}
    ], "name": "Transfer", "type": "event"},
]

# ==================== EMARE REWARD POOL ABI ====================
EMARE_REWARD_POOL_ABI = [
    # Okuma
    {"inputs": [], "name": "merkleRoot", "outputs": [{"type": "bytes32"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "epToEmrRate", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "dailyClaimLimit", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "monthlyEmissionCap", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "mintMode", "outputs": [{"type": "bool"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "currentMonthEmission", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"name": "", "type": "address"}], "name": "users",
     "outputs": [
         {"name": "totalClaimed", "type": "uint256"},
         {"name": "dailyClaimed", "type": "uint256"},
         {"name": "lastClaimDay", "type": "uint256"},
         {"name": "registeredAt", "type": "uint256"},
         {"name": "fraudScore", "type": "uint8"},
         {"name": "blacklisted", "type": "bool"},
         {"name": "cumulativeEpClaimed", "type": "uint256"},
     ], "stateMutability": "view", "type": "function"},
    {"inputs": [{"name": "", "type": "address"}], "name": "oracles",
     "outputs": [{"type": "bool"}], "stateMutability": "view", "type": "function"},
    # Yazma — Oracle (Cloud backend)
    {"inputs": [
        {"name": "user", "type": "address"},
        {"name": "epAmount", "type": "uint256"},
        {"name": "claimType", "type": "string"},
    ], "name": "oracleClaim", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [{"name": "newRoot", "type": "bytes32"}],
     "name": "updateMerkleRoot", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [
        {"name": "user", "type": "address"},
        {"name": "score", "type": "uint8"},
    ], "name": "setFraudScore", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [{"name": "user", "type": "address"}],
     "name": "registerUser", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    # Events
    {"anonymous": False, "inputs": [
        {"indexed": True, "name": "user", "type": "address"},
        {"indexed": False, "name": "epAmount", "type": "uint256"},
        {"indexed": False, "name": "emrAmount", "type": "uint256"},
        {"indexed": False, "name": "claimType", "type": "string"},
    ], "name": "RewardClaimed", "type": "event"},
    {"anonymous": False, "inputs": [
        {"indexed": True, "name": "user", "type": "address"},
    ], "name": "UserRegistered", "type": "event"},
]

# ==================== EMARE MARKETPLACE ABI ====================
EMARE_MARKETPLACE_ABI = [
    # Okuma
    {"inputs": [{"name": "", "type": "uint256"}], "name": "products",
     "outputs": [
         {"name": "id", "type": "uint256"},
         {"name": "creator", "type": "address"},
         {"name": "metadata", "type": "string"},
         {"name": "price", "type": "uint256"},
         {"name": "productType", "type": "uint8"},
         {"name": "active", "type": "bool"},
         {"name": "totalSales", "type": "uint256"},
         {"name": "totalRevenue", "type": "uint256"},
         {"name": "totalRefunds", "type": "uint256"},
         {"name": "ratingSum", "type": "uint256"},
         {"name": "ratingCount", "type": "uint256"},
         {"name": "createdAt", "type": "uint256"},
     ], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "nextProductId", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "creatorShareBps", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "platformShareBps", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "rewardPoolShareBps", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"name": "", "type": "uint256"}, {"name": "", "type": "address"}],
     "name": "hasPurchased", "outputs": [{"type": "bool"}], "stateMutability": "view", "type": "function"},
    # Events
    {"anonymous": False, "inputs": [
        {"indexed": True, "name": "productId", "type": "uint256"},
        {"indexed": True, "name": "creator", "type": "address"},
        {"indexed": False, "name": "price", "type": "uint256"},
        {"indexed": False, "name": "productType", "type": "uint8"},
    ], "name": "ProductListed", "type": "event"},
    {"anonymous": False, "inputs": [
        {"indexed": True, "name": "purchaseId", "type": "uint256"},
        {"indexed": True, "name": "productId", "type": "uint256"},
        {"indexed": True, "name": "buyer", "type": "address"},
        {"indexed": False, "name": "amount", "type": "uint256"},
    ], "name": "ProductPurchased", "type": "event"},
]

# ==================== EMARE SETTLEMENT ABI ====================
EMARE_SETTLEMENT_ABI = [
    # Okuma
    {"inputs": [{"name": "", "type": "uint256"}], "name": "orders",
     "outputs": [
         {"name": "id", "type": "uint256"},
         {"name": "buyer", "type": "address"},
         {"name": "seller", "type": "address"},
         {"name": "amount", "type": "uint256"},
         {"name": "platformFee", "type": "uint256"},
         {"name": "status", "type": "uint8"},
         {"name": "createdAt", "type": "uint256"},
         {"name": "deadline", "type": "uint256"},
         {"name": "metadata", "type": "string"},
     ], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "nextOrderId", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "platformFeeBps", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    # Events
    {"anonymous": False, "inputs": [
        {"indexed": True, "name": "orderId", "type": "uint256"},
        {"indexed": True, "name": "buyer", "type": "address"},
        {"indexed": True, "name": "seller", "type": "address"},
        {"indexed": False, "name": "amount", "type": "uint256"},
    ], "name": "OrderCreated", "type": "event"},
    {"anonymous": False, "inputs": [
        {"indexed": True, "name": "orderId", "type": "uint256"},
        {"indexed": False, "name": "sellerAmount", "type": "uint256"},
        {"indexed": False, "name": "feeAmount", "type": "uint256"},
    ], "name": "OrderCompleted", "type": "event"},
]
