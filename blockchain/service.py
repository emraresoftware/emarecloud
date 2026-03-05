"""
EmareCloud — Blockchain Servis Katmanı
Web3 üzerinden EmareToken ekosistemiyle etkileşim.

Bu modül, Cloud backend'in akıllı kontratlarla iletişim kurmasını sağlar:
- Token bakiyesi sorgulama
- RewardPool oracle claim (EP→EMR)
- Marketplace ürün sorgulama
- Settlement sipariş durumu
- Merkle root güncelleme (RewardPool)
"""

import logging
from decimal import Decimal
from typing import Optional

logger = logging.getLogger('emarecloud.blockchain')


class BlockchainService:
    """
    EmareToken ekosistemiyle etkileşim servisi.

    Kullanım:
        from blockchain.service import blockchain_service
        balance = blockchain_service.get_token_balance('0x...')
    """

    def __init__(self):
        self._web3 = None
        self._token_contract = None
        self._reward_pool_contract = None
        self._marketplace_contract = None
        self._settlement_contract = None
        self._initialized = False
        self._config = {}

    def init_app(self, app):
        """Flask uygulamasıyla entegre eder."""
        self._config = {
            'rpc_url': app.config.get('BLOCKCHAIN_RPC_URL', ''),
            'chain_id': app.config.get('BLOCKCHAIN_CHAIN_ID', 97),
            'token_address': app.config.get('EMARE_TOKEN_ADDRESS', ''),
            'reward_pool_address': app.config.get('EMARE_REWARD_POOL_ADDRESS', ''),
            'marketplace_address': app.config.get('EMARE_MARKETPLACE_ADDRESS', ''),
            'settlement_address': app.config.get('EMARE_SETTLEMENT_ADDRESS', ''),
            'oracle_private_key': app.config.get('BLOCKCHAIN_ORACLE_PRIVATE_KEY', ''),
            'payment_address': app.config.get('EMARE_PAYMENT_ADDRESS', ''),
            'enabled': app.config.get('BLOCKCHAIN_ENABLED', False),
        }

        if not self._config['enabled']:
            logger.info("⛓️  Blockchain entegrasyonu devre dışı (BLOCKCHAIN_ENABLED=false)")
            return

        if not self._config['rpc_url']:
            logger.warning("⛓️  Blockchain RPC URL yapılandırılmamış")
            return

        try:
            self._initialize_web3()
            logger.info(f"⛓️  Blockchain bağlantısı aktif — Chain ID: {self._config['chain_id']}")
        except Exception as e:
            logger.error(f"⛓️  Blockchain başlatma hatası: {e}")

    def _initialize_web3(self):
        """Web3 bağlantısını ve kontratları başlatır."""
        try:
            from web3 import Web3
        except ImportError:
            logger.error("web3 paketi yüklü değil. 'pip install web3' ile yükleyin.")
            return

        from blockchain.contracts import (
            EMARE_MARKETPLACE_ABI,
            EMARE_REWARD_POOL_ABI,
            EMARE_SETTLEMENT_ABI,
            EMARE_TOKEN_ABI,
        )

        rpc_url = self._config['rpc_url']

        if rpc_url.startswith('ws'):
            self._web3 = Web3(Web3.WebsocketProvider(rpc_url))
        else:
            self._web3 = Web3(Web3.HTTPProvider(rpc_url))

        if not self._web3.is_connected():
            logger.error(f"⛓️  RPC bağlantısı başarısız: {rpc_url}")
            return

        # Kontratları başlat
        w3 = self._web3
        checksum = w3.to_checksum_address

        if self._config['token_address']:
            self._token_contract = w3.eth.contract(
                address=checksum(self._config['token_address']),
                abi=EMARE_TOKEN_ABI,
            )

        if self._config['reward_pool_address']:
            self._reward_pool_contract = w3.eth.contract(
                address=checksum(self._config['reward_pool_address']),
                abi=EMARE_REWARD_POOL_ABI,
            )

        if self._config['marketplace_address']:
            self._marketplace_contract = w3.eth.contract(
                address=checksum(self._config['marketplace_address']),
                abi=EMARE_MARKETPLACE_ABI,
            )

        if self._config['settlement_address']:
            self._settlement_contract = w3.eth.contract(
                address=checksum(self._config['settlement_address']),
                abi=EMARE_SETTLEMENT_ABI,
            )

        self._initialized = True

    @property
    def is_available(self) -> bool:
        """Blockchain servisi kullanılabilir mi?"""
        return self._initialized and self._web3 is not None and self._web3.is_connected()

    # ==================== TOKEN İŞLEMLERİ ====================

    def get_token_balance(self, wallet_address: str) -> Optional[Decimal]:
        """Kullanıcının EMARE token bakiyesini döndürür (insan okunabilir)."""
        if not self.is_available or not self._token_contract:
            return None
        try:
            checksum = self._web3.to_checksum_address(wallet_address)
            raw_balance = self._token_contract.functions.balanceOf(checksum).call()
            return Decimal(raw_balance) / Decimal(10 ** 18)
        except Exception as e:
            logger.error(f"Token bakiye sorgu hatası [{wallet_address}]: {e}")
            return None

    def get_token_info(self) -> Optional[dict]:
        """Token genel bilgilerini döndürür."""
        if not self.is_available or not self._token_contract:
            return None
        try:
            total_supply_raw = self._token_contract.functions.totalSupply().call()
            max_supply_raw = self._token_contract.functions.MAX_SUPPLY().call()
            paused = self._token_contract.functions.paused().call()
            return {
                'name': 'EmareToken',
                'symbol': 'EMARE',
                'decimals': 18,
                'total_supply': str(Decimal(total_supply_raw) / Decimal(10 ** 18)),
                'max_supply': str(Decimal(max_supply_raw) / Decimal(10 ** 18)),
                'paused': paused,
                'contract_address': self._config['token_address'],
            }
        except Exception as e:
            logger.error(f"Token bilgi sorgu hatası: {e}")
            return None

    # ==================== REWARD POOL İŞLEMLERİ ====================

    def get_reward_pool_info(self) -> Optional[dict]:
        """RewardPool kontrat bilgilerini döndürür."""
        if not self.is_available or not self._reward_pool_contract:
            return None
        try:
            rp = self._reward_pool_contract.functions
            ep_rate = rp.epToEmrRate().call()
            daily_limit_raw = rp.dailyClaimLimit().call()
            monthly_cap_raw = rp.monthlyEmissionCap().call()
            current_emission_raw = rp.currentMonthEmission().call()
            mint_mode = rp.mintMode().call()
            return {
                'ep_to_emr_rate': ep_rate,
                'daily_claim_limit': str(Decimal(daily_limit_raw) / Decimal(10 ** 18)),
                'monthly_emission_cap': str(Decimal(monthly_cap_raw) / Decimal(10 ** 18)),
                'current_month_emission': str(Decimal(current_emission_raw) / Decimal(10 ** 18)),
                'mint_mode': mint_mode,
                'contract_address': self._config['reward_pool_address'],
            }
        except Exception as e:
            logger.error(f"RewardPool bilgi sorgu hatası: {e}")
            return None

    def get_user_reward_info(self, wallet_address: str) -> Optional[dict]:
        """Kullanıcının RewardPool verilerini döndürür."""
        if not self.is_available or not self._reward_pool_contract:
            return None
        try:
            checksum = self._web3.to_checksum_address(wallet_address)
            user_info = self._reward_pool_contract.functions.users(checksum).call()
            return {
                'total_claimed': str(Decimal(user_info[0]) / Decimal(10 ** 18)),
                'daily_claimed': str(Decimal(user_info[1]) / Decimal(10 ** 18)),
                'last_claim_day': user_info[2],
                'registered_at': user_info[3],
                'fraud_score': user_info[4],
                'blacklisted': user_info[5],
                'cumulative_ep_claimed': str(Decimal(user_info[6]) / Decimal(10 ** 18)),
            }
        except Exception as e:
            logger.error(f"RewardPool kullanıcı sorgu hatası [{wallet_address}]: {e}")
            return None

    def oracle_claim_reward(self, user_address: str, ep_amount: int, claim_type: str) -> Optional[str]:
        """
        Oracle olarak kullanıcıya EP→EMR ödülü verir.

        Args:
            user_address: Kullanıcının cüzdan adresi
            ep_amount: Kazanılan EP miktarı
            claim_type: "cashback" | "marketplace" | "work"

        Returns:
            Transaction hash veya None
        """
        if not self.is_available or not self._reward_pool_contract:
            return None
        if not self._config['oracle_private_key']:
            logger.error("Oracle private key yapılandırılmamış")
            return None
        try:
            w3 = self._web3
            account = w3.eth.account.from_key(self._config['oracle_private_key'])
            checksum = w3.to_checksum_address(user_address)

            tx = self._reward_pool_contract.functions.oracleClaim(
                checksum, ep_amount, claim_type
            ).build_transaction({
                'from': account.address,
                'nonce': w3.eth.get_transaction_count(account.address),
                'gas': 200000,
                'gasPrice': w3.eth.gas_price,
                'chainId': self._config['chain_id'],
            })

            signed = account.sign_transaction(tx)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            logger.info(f"⛓️  Oracle claim gönderildi: {tx_hash.hex()} — user={user_address}, ep={ep_amount}")
            return tx_hash.hex()
        except Exception as e:
            logger.error(f"Oracle claim hatası: {e}")
            return None

    def register_user_on_chain(self, wallet_address: str) -> Optional[str]:
        """Kullanıcıyı RewardPool kontratına kaydeder."""
        if not self.is_available or not self._reward_pool_contract:
            return None
        if not self._config['oracle_private_key']:
            return None
        try:
            w3 = self._web3
            account = w3.eth.account.from_key(self._config['oracle_private_key'])
            checksum = w3.to_checksum_address(wallet_address)

            tx = self._reward_pool_contract.functions.registerUser(
                checksum
            ).build_transaction({
                'from': account.address,
                'nonce': w3.eth.get_transaction_count(account.address),
                'gas': 150000,
                'gasPrice': w3.eth.gas_price,
                'chainId': self._config['chain_id'],
            })

            signed = account.sign_transaction(tx)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            logger.info(f"⛓️  Kullanıcı zincire kaydedildi: {tx_hash.hex()} — {wallet_address}")
            return tx_hash.hex()
        except Exception as e:
            logger.error(f"Kullanıcı kayıt hatası: {e}")
            return None

    def update_merkle_root(self, new_root: bytes) -> Optional[str]:
        """RewardPool Merkle root'unu günceller."""
        if not self.is_available or not self._reward_pool_contract:
            return None
        if not self._config['oracle_private_key']:
            return None
        try:
            w3 = self._web3
            account = w3.eth.account.from_key(self._config['oracle_private_key'])

            tx = self._reward_pool_contract.functions.updateMerkleRoot(
                new_root
            ).build_transaction({
                'from': account.address,
                'nonce': w3.eth.get_transaction_count(account.address),
                'gas': 100000,
                'gasPrice': w3.eth.gas_price,
                'chainId': self._config['chain_id'],
            })

            signed = account.sign_transaction(tx)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            logger.info(f"⛓️  Merkle root güncellendi: {tx_hash.hex()}")
            return tx_hash.hex()
        except Exception as e:
            logger.error(f"Merkle root güncelleme hatası: {e}")
            return None

    # ==================== MARKETPLACE İŞLEMLERİ ====================

    def get_marketplace_product(self, product_id: int) -> Optional[dict]:
        """On-chain marketplace ürün bilgisini döndürür."""
        if not self.is_available or not self._marketplace_contract:
            return None
        try:
            p = self._marketplace_contract.functions.products(product_id).call()
            product_types = ['AIModel', 'Template', 'Microservice', 'Dataset']
            return {
                'id': p[0],
                'creator': p[1],
                'metadata': p[2],
                'price': str(Decimal(p[3]) / Decimal(10 ** 18)),
                'product_type': product_types[p[4]] if p[4] < len(product_types) else 'Unknown',
                'active': p[5],
                'total_sales': p[6],
                'total_revenue': str(Decimal(p[7]) / Decimal(10 ** 18)),
                'total_refunds': p[8],
                'rating_sum': p[9],
                'rating_count': p[10],
                'average_rating': round(p[9] / p[10], 1) if p[10] > 0 else 0,
                'created_at': p[11],
            }
        except Exception as e:
            logger.error(f"Marketplace ürün sorgu hatası [#{product_id}]: {e}")
            return None

    def get_marketplace_stats(self) -> Optional[dict]:
        """Marketplace genel istatistiklerini döndürür."""
        if not self.is_available or not self._marketplace_contract:
            return None
        try:
            mp = self._marketplace_contract.functions
            next_id = mp.nextProductId().call()
            creator_share = mp.creatorShareBps().call()
            platform_share = mp.platformShareBps().call()
            reward_pool_share = mp.rewardPoolShareBps().call()
            return {
                'total_products': next_id - 1,
                'creator_share_percent': creator_share / 100,
                'platform_share_percent': platform_share / 100,
                'reward_pool_share_percent': reward_pool_share / 100,
                'contract_address': self._config['marketplace_address'],
            }
        except Exception as e:
            logger.error(f"Marketplace istatistik hatası: {e}")
            return None

    # ==================== SETTLEMENT İŞLEMLERİ ====================

    def get_settlement_order(self, order_id: int) -> Optional[dict]:
        """Escrow siparişi bilgisini döndürür."""
        if not self.is_available or not self._settlement_contract:
            return None
        try:
            order_statuses = ['Created', 'Delivered', 'Completed', 'Disputed', 'Resolved', 'Cancelled', 'Expired']
            o = self._settlement_contract.functions.orders(order_id).call()
            return {
                'id': o[0],
                'buyer': o[1],
                'seller': o[2],
                'amount': str(Decimal(o[3]) / Decimal(10 ** 18)),
                'platform_fee': str(Decimal(o[4]) / Decimal(10 ** 18)),
                'status': order_statuses[o[5]] if o[5] < len(order_statuses) else 'Unknown',
                'created_at': o[6],
                'deadline': o[7],
                'metadata': o[8],
            }
        except Exception as e:
            logger.error(f"Settlement sipariş sorgu hatası [#{order_id}]: {e}")
            return None

    def get_settlement_stats(self) -> Optional[dict]:
        """Settlement genel istatistiklerini döndürür."""
        if not self.is_available or not self._settlement_contract:
            return None
        try:
            st = self._settlement_contract.functions
            next_id = st.nextOrderId().call()
            fee_bps = st.platformFeeBps().call()
            return {
                'total_orders': next_id - 1,
                'platform_fee_percent': fee_bps / 100,
                'contract_address': self._config['settlement_address'],
            }
        except Exception as e:
            logger.error(f"Settlement istatistik hatası: {e}")
            return None

    # ==================== TOKEN ÖDEME DOĞRULAMA ====================

    def verify_token_payment(
        self,
        tx_hash: str,
        expected_from: str,
        expected_to: str,
        expected_amount_emare: float,
        tolerance_percent: float = 1.0,
    ) -> dict:
        """
        Bir EMARE token transfer işlemini doğrular.

        Args:
            tx_hash: İşlem hash'i (0x ile başlamalı)
            expected_from: Gönderenin beklenen cüzdan adresi
            expected_to: Alıcının beklenen cüzdan adresi (ödeme adresi)
            expected_amount_emare: Beklenen EMARE miktarı (örn: 490.0)
            tolerance_percent: İzin verilen sapma yüzdesi (varsayılan %1)

        Returns:
            {'valid': bool, 'reason': str, 'actual_amount': float, 'block': int}
        """
        if not self.is_available or not self._token_contract:
            return {'valid': False, 'reason': 'Blockchain bağlantısı yok', 'actual_amount': 0, 'block': 0}

        try:
            w3 = self._web3

            # TX hash'i bytes'a çevir
            tx_hash_bytes = w3.to_bytes(hexstr=tx_hash)
            receipt = w3.eth.get_transaction_receipt(tx_hash_bytes)

            if receipt is None:
                return {'valid': False, 'reason': 'İşlem henüz onaylanmadı (pending)', 'actual_amount': 0, 'block': 0}

            if receipt['status'] != 1:
                return {'valid': False, 'reason': 'İşlem başarısız (reverted)', 'actual_amount': 0, 'block': receipt['blockNumber']}

            # Transfer event'lerini parse et
            token_address = self._config['token_address']
            transfer_events = self._token_contract.events.Transfer().process_receipt(receipt)

            if not transfer_events:
                return {'valid': False, 'reason': 'Transfer event bulunamadı', 'actual_amount': 0, 'block': receipt['blockNumber']}

            # Token adresini kontrol et
            if receipt['to'] and receipt['to'].lower() != token_address.lower():
                return {'valid': False, 'reason': 'Yanlış token kontrat adresi', 'actual_amount': 0, 'block': receipt['blockNumber']}

            # Transfer event içinde beklenen adresleri kontrol et
            checksum_from = w3.to_checksum_address(expected_from)
            checksum_to = w3.to_checksum_address(expected_to)

            valid_transfer = None
            for event in transfer_events:
                args = event['args']
                if (args['from'].lower() == checksum_from.lower() and
                        args['to'].lower() == checksum_to.lower()):
                    valid_transfer = event
                    break

            if not valid_transfer:
                return {
                    'valid': False,
                    'reason': f'Beklenen gönderici/alıcı eşleşmiyor (from={expected_from[:10]}... to={expected_to[:10]}...)',
                    'actual_amount': 0,
                    'block': receipt['blockNumber'],
                }

            # Miktar kontrolü
            actual_raw = valid_transfer['args']['value']
            actual_amount = float(Decimal(actual_raw) / Decimal(10 ** 18))

            lower = expected_amount_emare * (1 - tolerance_percent / 100)
            upper = expected_amount_emare * (1 + tolerance_percent / 100)

            if not (lower <= actual_amount <= upper):
                return {
                    'valid': False,
                    'reason': f'Yanlış miktar: beklenen ≈{expected_amount_emare} EMARE, gelen {actual_amount:.2f} EMARE',
                    'actual_amount': actual_amount,
                    'block': receipt['blockNumber'],
                }

            logger.info(
                f"⛓️  Token ödeme doğrulandı: tx={tx_hash[:16]}... "
                f"from={expected_from[:10]}... amount={actual_amount} EMARE"
            )
            return {
                'valid': True,
                'reason': 'Ödeme doğrulandı',
                'actual_amount': actual_amount,
                'block': receipt['blockNumber'],
            }

        except Exception as e:
            logger.error(f"Token ödeme doğrulama hatası [{tx_hash}]: {e}")
            return {'valid': False, 'reason': f'Doğrulama hatası: {str(e)}', 'actual_amount': 0, 'block': 0}

    def get_payment_address(self) -> str:
        """Abonelik ödemeleri için ödeme adresini döndürür (deployer/fee collector)."""
        return self._config.get('payment_address', '')


# Singleton instance — blockchain_service
blockchain_service = BlockchainService()
