import time
import requests
import settings
import random
from settings import SLEEP_TIME_MIN, SLEEP_TIME_MAX
from random import choice, randint
from rich.console import Console
from rich.progress import track
from rich import box
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.progress import Progress, SpinnerColumn, BarColumn, TimeElapsedColumn
from fake_useragent import UserAgent
from eth_account import Account
from eth_account.messages import encode_defunct
from web3 import Web3
from requests.exceptions import ProxyError, RequestException

# Инициализация консоли для вывода
console = Console()

# Initialize variables
ua = UserAgent()
base_url = "https://api.rabby.io/v1/"
#required_balance = settings.TRANSFER_AMOUNT * 10**6

def get_transfer_amount():
    # Если указано фиксированное значение, используем его
    if settings.FIXED_TRANSFER_AMOUNT is not None:
        return settings.FIXED_TRANSFER_AMOUNT * 10**6
    # Иначе выбираем случайное значение из диапазона
    elif settings.TRANSFER_AMOUNT_RANGE is not None:
        return random.randint(settings.TRANSFER_AMOUNT_RANGE[0], settings.TRANSFER_AMOUNT_RANGE[1]) * 10**6
    else:
        raise ValueError("Необходимо указать либо фиксированное значение, либо диапазон в settings.py")

# ABI для вызова balanceOf
token_abi = [
    {"constant": True, "inputs": [{"name": "account", "type": "address"}], "name": "balanceOf", "outputs": [{"name": "", "type": "uint256"}], "payable": False, "stateMutability": "view", "type": "function"},
    {"constant": False, "inputs": [{"name": "_to", "type": "address"}, {"name": "_value", "type": "uint256"}], "name": "transfer", "outputs": [{"name": "", "type": "bool"}], "payable": False, "stateMutability": "nonpayable", "type": "function"}
]



# Read private keys from the file
def read_keys(filename):
    with open(filename, 'r') as file:
        return [line.strip() for line in file.readlines()]

# Read proxies from the file
def read_proxies(filename):
    with open(filename, 'r') as file:
        return [line.strip() for line in file.readlines()]


# Get a dictionary for proxy use
def get_proxy(proxy_line):
    ip, port, username, password = proxy_line.split(":")
    proxy = {
        "http": f"socks5://{username}:{password}@{ip}:{port}",
        "https": f"socks5://{username}:{password}@{ip}:{port}"
    }
    return proxy


# Retry request with next proxy on failure
def make_request_with_proxy(url, method="GET", headers=None, data=None, proxies=None):
    for proxy_line in proxies:
        proxy = get_proxy(proxy_line)
        try:
            if method == "GET":
                response = requests.get(url, headers=headers, proxies=proxy, timeout=10)
            elif method == "POST":
                response = requests.post(url, headers=headers, json=data, proxies=proxy, timeout=10)
            response.raise_for_status()  # Will raise an exception for HTTP errors
            return response.json()  # Return response if successful
        except (ProxyError, RequestException) as e:
            print(f"Ошибка с прокси {proxy_line}: {e}")
            # Continue to the next proxy
            continue
    raise Exception("Все прокси не сработали.")


# Контрактные адреса и RPC для разных сетей
networks = {
    "arb": {
        "rpc": "https://1rpc.io/arb",
        "tokens": {
            "USDC": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
            "USDT": "0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9"
        },
        "vault_contract": "0x40F480F247f3aD2fF4c1463E84f03Be3A9a03E15",
        "chain_id": 42161
    },
    "op": {
        "rpc": "https://1rpc.io/op",
        "tokens": {
            "USDC": "0x0b2C639c533813f4Aa9D7837CAf62653d097Ff85",
            "USDT": "0x94b008aA00579c1307B0EF2c499aD98a8ce58e58"
        },
        "vault_contract": "0x824a2D0AE45c447CaA8D0DA4BB68a1a0056CAdC6",
        "chain_id": 10
    },
    "matic": {
        "rpc": "https://polygon.drpc.org",
        "tokens": {
            "USDC": "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359",
            "USDT": "0xc2132D05D31c914a87C6611C10748AEb04B58e8F"
        },
        "vault_contract": "0xdE74F4eFDeec194c3f7b26bE736BC8B5266FF7A5",
        "chain_id": 137
    },
    "bsc": {
        "rpc": "https://1rpc.io/bnb",
        "tokens": {
            "USDC": "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d"
        },
        "vault_contract": "0x293391044c6981b6417fA0Dcfd85524d4098A8d6",
        "chain_id": 56
    },
    "eth": {
        "rpc": "https://1rpc.io/eth",
        "tokens": {
            "USDC": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
            "USDT": "0xdAC17F958D2ee523a2206206994597C13D831ec7"
        },
        "vault_contract": "0x205E94337bC61657b4b698046c3c2c5C1d2Fb8F1",
        "chain_id": 1
    },
    "base": {
        "rpc": "https://1rpc.io/base",
        "tokens": {
            "USDC": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
        },
        "vault_contract": "0x16Ac3457ce84E6c5f80b394C59ccb2FD17049a62",
        "chain_id": 8453
    }
}


# Read private keys from the file
def read_keys(filename):
    with open(filename, 'r') as file:
        return [line.strip() for line in file.readlines()]


# Проверка баланса USDC токенов в каждой сети
def check_token_balance(wallet_address, rpc_url, token_contract_address):
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    token_contract = w3.eth.contract(address=w3.to_checksum_address(token_contract_address), abi=token_abi)
    balance = token_contract.functions.balanceOf(wallet_address).call()
    return balance

# Выполнение перевода токена в выбранной сети
def transfer_token(wallet_address, private_key, amount, network_data, token_address):
    w3 = Web3(Web3.HTTPProvider(network_data['rpc']))
    nonce = w3.eth.get_transaction_count(wallet_address)

    gas_price = w3.eth.gas_price
    token_contract = w3.eth.contract(address=w3.to_checksum_address(token_address), abi=token_abi)

    transaction = token_contract.functions.transfer(
        w3.to_checksum_address(network_data['vault_contract']), amount
    ).build_transaction({
        'from': wallet_address,
        'gasPrice': int(gas_price * 1.2),
        'nonce': nonce,
        'chainId': network_data['chain_id']
    })

    gas_limit = w3.eth.estimate_gas(transaction)
    transaction['gas'] = gas_limit

    signed_txn = w3.eth.account.sign_transaction(transaction, private_key=private_key)
    txid = w3.eth.send_raw_transaction(signed_txn.rawTransaction)
    return w3.to_hex(txid), nonce


# Подписание сообщения с помощью приватного ключа
def sign_message(private_key, message_text):
    account = Account.from_key(private_key)
    message = encode_defunct(text=message_text)
    signed_message = Account.sign_message(message, private_key=private_key)
    return signed_message.signature.hex()


# 1. Login: Get sign text
def login_step_1(wallet_address, proxies):
    timestamp = int(time.time())
    url = f"{base_url}gas_account/sign_text?account_id={wallet_address}"
    headers = {
        'user-agent': ua.random,
        'x-api-nonce': 'n_y0hUxhARzBLty7tvmeDTadO4olQXyeW0J1VWa2iB',  # Пример nonce
        'x-api-sign': 'c631a6440d2ae5d5dcb3c971b226554e4d4a3cd0da3e4a3a1fef2ad01a978212',
        'x-api-ts': str(timestamp),
        'x-api-ver': 'v2',
        'x-client': 'Rabby',
        'x-version': '0.92.90'
    }
    return make_request_with_proxy(url, method="GET", headers=headers, proxies=proxies)


# 2. Отправляем POST данные для проверки текста входа
def login_step_2(wallet_address, message_text, proxies):
    timestamp = int(time.time())
    url = f"{base_url}engine/action/parse_text"
    headers = {
        'user-agent': ua.random,
        'x-api-nonce': 'n_VZPwz29FKupfeEKdTFvgAVbN2MKa2hObe2d0XSIp',
        'x-api-sign': '65fa7df8042c1ba6b325416aa1efc1d02e25629e2e224108b5ea57aba1560e1f',
        'x-api-ts': str(timestamp),
        'x-api-ver': 'v2',
        'x-client': 'Rabby',
        'x-version': '0.92.90'
    }
    data = {
        "text": message_text,
        "origin": "chrome-extension://acmacodkjbdgmoleebolmdjonilkdbch",
        "user_addr": wallet_address
    }
    return make_request_with_proxy(url, method="POST", headers=headers, data=data, proxies=proxies)


# 3. Завершаем логин (sig передаем через headers)
def login_step_3(wallet_address, signature, proxies):
    timestamp = int(time.time())
    url = f"{base_url}gas_account/login"
    headers = {
        'sig': signature,
        'user-agent': ua.random,
        'x-api-nonce': 'n_aKsnBpDyWAhbT6FGN8dnrQGeNJvyohWt7nZmH3Iq',
        'x-api-sign': 'a1a6041d5c54bd8d7590a22c6e977b59947bdfd98465b28fbff6398d65cee9ed',
        'x-api-ts': str(timestamp),
        'x-api-ver': 'v2',
        'x-client': 'Rabby',
        'x-version': '0.92.90'
    }
    data = {
        "account_id": wallet_address
    }
    return make_request_with_proxy(url, method="POST", headers=headers, data=data, proxies=proxies)


# 4. Проверка баланса GAS ACCOUNT (GET запрос, используя ту же сигнатуру)
def check_gas_account_balance(wallet_address, signature, proxies):
    timestamp = int(time.time())
    url = f"{base_url}gas_account?id={wallet_address}"
    headers = {
        'sig': signature,  # Используем ту же сигнатуру
        'user-agent': ua.random,
        'x-api-nonce': 'n_TQTG7RXqHZtNnfmxVxVaU4uWkzUEFA6vIokgQOrQ',
        'x-api-sign': '94088b86593fd96ecb7e21c93bf6c1895cda1b1f7716d0c4a7c3d2030d9632a5',
        'x-api-ts': str(timestamp),
        'x-api-ver': 'v2',
        'x-client': 'Rabby',
        'x-version': '0.92.90'
    }
    return make_request_with_proxy(url, method="GET", headers=headers, proxies=proxies)


# 5. Функция для отправки POST-запроса на recharge
def send_recharge_request(wallet_address, txid, nonce, signature, chain_id, proxies):
    url = f"{base_url}gas_account/recharge"
    timestamp = int(time.time())

    # POST данные
    data = {
        "account_id": wallet_address,
        "tx_id": txid,
        "chain_id": chain_id,  # Динамически передаём chain_id для соответствующей сети
        "amount": 20,  # Пополняем на 20 USDC
        "user_addr": wallet_address,
        "nonce": nonce
    }

    # Заголовки
    headers = {
        'sig': signature,
        'user-agent': ua.random,
        'x-api-nonce': 'n_D1UU490EVMkEq8g5T4xK6pCaRLFPrwD0kPvnI4VC',
        'x-api-sign': '01911af7b6f44fcf3a3225bd82835088f850f32a6a3314559f8ec2fec10f3888',
        'x-api-ts': str(timestamp),
        'x-api-ver': 'v2',
        'x-client': 'Rabby',
        'x-version': '0.92.89'
    }

    # Отправка POST-запроса
    response = make_request_with_proxy(url, method="POST", headers=headers, data=data, proxies=proxies)
    return response



# Основной цикл для обработки ключей
# Основной цикл для обработки ключей
def main():
    keys = read_keys("keys.txt")
    proxies = read_proxies("proxies.txt")  # Чтение прокси из файла
    total_wallets = len(keys)
    required_balance = get_transfer_amount()

    # Выводим общее количество кошельков
    console.print(f"[bold cyan]Total number of wallets:[/bold cyan] {total_wallets}")

    for idx, key in enumerate(keys, 1):
        account = Account.from_key(key)
        wallet_address = account.address

        # Панель для текущего кошелька
        console.rule(f"[bold green]Processing wallet {idx}/{total_wallets}: {wallet_address}")

        # Проверяем баланс токенов в каждой сети
        available_options = []
        for network, data in networks.items():
            for token_name, token_address in data["tokens"].items():
                balance = check_token_balance(wallet_address, data['rpc'], token_address)
                console.print(f"[bold magenta]Balance of {token_name} in {network}:[/bold magenta] {balance / 10 ** 6:.2f} {token_name}")
                if balance >= required_balance:
                    available_options.append((network, token_name, token_address))

        if not available_options:
            console.print(f"[bold red]Not enough tokens in wallet:[/bold red] {wallet_address}")
            continue

        # Выбор сети и токена
        selected_network, selected_token, token_address = choice(available_options)
        network_data = networks[selected_network]
        console.print(f"[bold blue]Network selected[/bold blue] - {selected_network.capitalize()} with token {selected_token}")

        # Шаги авторизации с прогрессом
        with Progress(
            SpinnerColumn(),
            "[progress.description]{task.description}",
            BarColumn(),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            progress.add_task("[cyan]Processing wallet...", total=None)

            # Шаг 1: Получаем текст для подписи
            sign_data = login_step_1(wallet_address, proxies)

            # Шаг 2: Проверяем текст на сервере
            login_check = login_step_2(wallet_address, sign_data["text"], proxies)

            # Подписание текста
            signature = sign_message(key, sign_data["text"])

            # Шаг 3: Завершаем логин
            login_result = login_step_3(wallet_address, signature, proxies)
            console.print(f"[bold green]Login response:[/bold green] {login_result}")

            # Шаг 4: Проверка баланса GAS ACCOUNT с той же сигнатурой
            balance_info = check_gas_account_balance(wallet_address, signature, proxies)
            console.print(f"[bold yellow]Balance Gas Account before deposit:[/bold yellow] {balance_info['account']['balance']}")

            # Выполняем перевод токена в выбранной сети и выводим информацию
            txid, nonce = transfer_token(wallet_address, key, required_balance, network_data, token_address)
            console.print(
                f"[bold green]Deposit fulfilled[/bold green] - {txid} | [bold yellow]Amount:[/bold yellow] [cyan]{required_balance / 10 ** 6:.2f}[/cyan] {selected_token} in [magenta]{selected_network.capitalize()}[/magenta]")

            # Отправляем запрос на пополнение (recharge)
            recharge_response = send_recharge_request(wallet_address, txid, nonce, signature, selected_network, proxies)

            if recharge_response.get("success"):
                console.print("[bold green]Recharge Success[/bold green]")
            else:
                console.print(f"[bold red]Error during recharge:[/bold red] {recharge_response}")

            # Ждем 15 секунд и проверяем баланс GAS ACCOUNT
            time.sleep(30)
            balance_info = check_gas_account_balance(wallet_address, signature, proxies)
            console.print(f"[bold cyan]Balance Gas Account is[/bold cyan] {balance_info['account']['balance']}")

        console.print(Panel(f"Work with wallet {wallet_address} is completed", style="bold green"))

        # Сон перед обработкой следующего кошелька
        sleep_time = randint(SLEEP_TIME_MIN, SLEEP_TIME_MAX)
        console.print(f"[bold cyan]Sleeping for {sleep_time} seconds before processing next wallet...[/bold cyan]")
        time.sleep(sleep_time)


if __name__ == "__main__":
    main()
