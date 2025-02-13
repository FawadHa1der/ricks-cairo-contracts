import logging
import pytest
import asyncio
from starkware.starknet.public.abi import get_selector_from_name
from starkware.starknet.testing.starknet import Starknet
from utils import (
    Signer, uint, str_to_felt, ZERO_ADDRESS, TRUE, FALSE, assert_revert, assert_event_emitted,
    get_contract_def, cached_contract, to_uint, sub_uint, add_uint, div_rem_uint, mul_uint
)

OwnerSigner = Signer(123456789987654321)
Account1Signer = Signer(123456789987654322)
Account2Signer = Signer(123456789987654323)

LOGGER = logging.getLogger(__name__)
# @pytest.fixture(scope='session')
# def logger():

#     logger = logging.getLogger('Some.Logger')
#     logger.setLevel(logging.INFO)

#     return logger


@pytest.fixture(scope='module')
def event_loop():
    return asyncio.new_event_loop()


@pytest.fixture(scope='module')
async def erc20_init(contract_defs):
    logging.getLogger().info('setup erc20 factory testfixture ')

    starknet = await Starknet.empty()
    account_def, erc20_def, stakingpool_def = contract_defs
    owner = await starknet.deploy(
        contract_def=account_def,
        constructor_calldata=[OwnerSigner.public_key]
    )

    account1 = await starknet.deploy(
        contract_def=account_def,
        constructor_calldata=[Account1Signer.public_key]
    )

    account2 = await starknet.deploy(
        contract_def=account_def,
        constructor_calldata=[Account2Signer.public_key]
    )

    erc20Stake = await starknet.deploy(
        contract_def=erc20_def,
        constructor_calldata=[
            str_to_felt("STAKE"),      # name
            str_to_felt("STK"),        # symbol
            18,                        # decimals
            *uint(1000),               # initial_supply
            owner.contract_address   # recipient
        ]
    )

    erc20Reward = await starknet.deploy(
        contract_def=erc20_def,
        constructor_calldata=[
            str_to_felt("Reward"),      # name
            str_to_felt("RWD"),        # symbol
            18,                        # decimals
            *uint(1000),               # initial_supply
            owner.contract_address   # recipient
        ]
    )

    stakingPool = await starknet.deploy(
        contract_def=stakingpool_def,
        constructor_calldata=[]
    )

    return starknet, starknet.state, erc20Stake, erc20Reward, stakingPool, owner,  account1, account2


@pytest.fixture(scope='module')
def contract_defs():
    account_def = get_contract_def('openzeppelin/account/Account.cairo')

    erc20_def = get_contract_def(
        'openzeppelin/token/erc20/ERC20.cairo')

    stakingpool_def = get_contract_def(
        'contracts/StakingPool.cairo')

    return account_def, erc20_def, stakingpool_def


@pytest.fixture
def erc20_factory(erc20_init, contract_defs):
    starknet, state, erc20Stake, erc20Reward, stakingPool, owner, account1, account2 = erc20_init
    account_def, erc20_def, stakingpool_def = contract_defs
    _state = state.copy()
    account1 = cached_contract(_state, account_def, account1)
    account2 = cached_contract(_state, account_def, account2)
    owner = cached_contract(_state, account_def, owner)
    erc20Stake = cached_contract(_state, erc20_def, erc20Stake)
    erc20Reward = cached_contract(_state, erc20_def, erc20Reward)
    stakingPool = cached_contract(_state, stakingpool_def, stakingPool)

    return starknet, owner, account1, account2, erc20Stake, erc20Reward, stakingPool


@pytest.fixture
async def after_initializer(erc20_factory):
    starknet, owner, account1, account2, erc20Stake, erc20Reward, stakingPool = erc20_factory
    return_bool = await OwnerSigner.send_transaction(owner, stakingPool.contract_address, 'pool_initialize', [erc20Stake.contract_address, erc20Reward.contract_address])
    # check return value equals true ('1')
    assert return_bool.result.response == [1]

    amount = uint(100)

    # transfer
    return_bool = await OwnerSigner.send_transaction(owner, erc20Stake.contract_address, 'transfer', [account1.contract_address, *amount])
    # check return value equals true ('1')
    assert return_bool.result.response == [1]

    # transfer
    return_bool = await OwnerSigner.send_transaction(owner, erc20Stake.contract_address, 'transfer', [account2.contract_address, *amount])
    # check return value equals true ('1')
    assert return_bool.result.response == [1]

    # approvals
    amount = uint(1000)
    # read the current allowance
    execution_info = await erc20Stake.allowance(account1.contract_address, stakingPool.contract_address).call()
    assert execution_info.result.remaining == uint(0)

    # set approval
    return_bool = await Account1Signer.send_transaction(account1, erc20Stake.contract_address, 'approve', [stakingPool.contract_address, *amount])
    # check return value equals true ('1')
    assert return_bool.result.response == [1]

    execution_info = await erc20Stake.allowance(account1.contract_address, stakingPool.contract_address).call()
    assert execution_info.result.remaining == amount

    # read the current allowance
    execution_info = await erc20Stake.allowance(account2.contract_address, stakingPool.contract_address).call()
    assert execution_info.result.remaining == uint(0)

    # set approval
    return_bool = await Account2Signer.send_transaction(account2, erc20Stake.contract_address, 'approve', [stakingPool.contract_address, *amount])
    # check return value equals true ('1')
    assert return_bool.result.response == [1]

    # set approval
    return_bool = await OwnerSigner.send_transaction(owner, erc20Reward.contract_address, 'approve', [stakingPool.contract_address, *amount])
    # check return value equals true ('1')
    assert return_bool.result.response == [1]

    execution_info = await erc20Stake.allowance(account2.contract_address, stakingPool.contract_address).call()
    assert execution_info.result.remaining == amount

    return starknet, erc20Stake, erc20Reward, stakingPool, owner, account1, account2


@pytest.mark.asyncio
async def test_constructor(after_initializer):
    starknet, erc20Stake, erc20Reward, stakingPool, owner, account1, account2 = after_initializer

    execution_info = await erc20Stake.balanceOf(account1.contract_address).call()
    assert execution_info.result.balance == uint(100)

    execution_info = await erc20Stake.balanceOf(account2.contract_address).call()
    assert execution_info.result.balance == uint(100)

    execution_info = await erc20Stake.balanceOf(owner.contract_address).call()
    assert execution_info.result.balance == uint(800)

    execution_info = await erc20Stake.totalSupply().call()
    assert execution_info.result.totalSupply == uint(1000)

    execution_info = await erc20Reward.totalSupply().call()
    assert execution_info.result.totalSupply == uint(1000)


@pytest.mark.asyncio
async def test_stake(after_initializer):
    starknet, erc20Stake, erc20Reward, stakingPool, owner, account1, account2 = after_initializer

    execution_info = await stakingPool.total_supply_staked().call()
    assert execution_info.result.supply == uint(0)

    amount = uint(10)

    # stake
    return_bool = await Account1Signer.send_transaction(account1, stakingPool.contract_address, 'stake', [*amount])
    # check return value equals true ('1')
    assert return_bool.result.response == [1]

    execution_info = await erc20Stake.balanceOf(account1.contract_address).call()
    assert execution_info.result.balance == uint(90)

    execution_info = await stakingPool.total_supply_staked().call()
    assert execution_info.result.supply == uint(10)


@pytest.mark.asyncio
async def test_depositRewards(after_initializer):
    starknet, erc20Stake, erc20Reward, stakingPool, owner, account1, account2 = after_initializer

    amount = uint(10)
    reward_amount = uint(100)

    # stake
    return_bool = await Account1Signer.send_transaction(account1, stakingPool.contract_address, 'stake', [*amount])
    # check return value equals true ('1')
    assert return_bool.result.response == [1]

    execution_info = await erc20Reward.balanceOf(owner.contract_address).call()
    reward_token_owner_initial_balance = execution_info.result.balance

    return_bool = await OwnerSigner.send_transaction(owner, stakingPool.contract_address, 'deposit_reward', [*reward_amount])
    # check return value equals true ('1')
    assert return_bool.result.response == [1]

    execution_info = await erc20Reward.balanceOf(owner.contract_address).call()
    reward_token_final_balance = execution_info.result.balance

    execution_info = await erc20Reward.balanceOf(stakingPool.contract_address).call()
    staking_pool_balance = execution_info.result.balance
    assert staking_pool_balance == reward_amount

    # expect(rewardTokenOwnerInitialBalance.sub(rewardAmount)).to.eq(rewardTokenOwnerFinalBalance);

    assert sub_uint(reward_token_owner_initial_balance,
                    reward_amount) == reward_token_final_balance


@pytest.mark.asyncio
async def test_depositRewards(after_initializer):
    starknet, erc20Stake, erc20Reward, stakingPool, owner, account1, account2 = after_initializer
    amount = uint(10)
    reward_amount = uint(100)

    # stake
    return_bool = await Account1Signer.send_transaction(account1, stakingPool.contract_address, 'stake', [*amount])
    # check return value equals true ('1')
    assert return_bool.result.response == [1]

    return_bool = await OwnerSigner.send_transaction(owner, stakingPool.contract_address, 'deposit_reward', [*reward_amount])
    # check return value equals true ('1')
    assert return_bool.result.response == [1]

    return_bool = await Account1Signer.send_transaction(account1, stakingPool.contract_address, 'unstake_claim_rewards', [])
    # check return value equals true ('1')
    assert return_bool.result.response == [1]

    execution_info = await erc20Reward.balanceOf(account1.contract_address).call()
    final_balance = execution_info.result.balance
    assert final_balance == reward_amount


@pytest.mark.asyncio
async def test_depositProportionalRewards(after_initializer):
    starknet, erc20Stake, erc20Reward, stakingPool, owner, account1, account2 = after_initializer
    stake_amount_account1 = uint(1)
    stake_amount_account2 = uint(4)

    total_stake = add_uint(stake_amount_account1, stake_amount_account2)

    # stake
    return_bool = await Account1Signer.send_transaction(account1, stakingPool.contract_address, 'stake', [*stake_amount_account1])
    # check return value equals true ('1')
    assert return_bool.result.response == [1]

    # stake
    return_bool = await Account2Signer.send_transaction(account2, stakingPool.contract_address, 'stake', [*stake_amount_account2])
    # check return value equals true ('1')
    assert return_bool.result.response == [1]

    reward_amount = uint(100)
    return_bool = await OwnerSigner.send_transaction(owner, stakingPool.contract_address, 'deposit_reward', [*reward_amount])
    # check return value equals true ('1')
    assert return_bool.result.response == [1]

    return_bool = await Account1Signer.send_transaction(account1, stakingPool.contract_address, 'unstake_claim_rewards', [])
    # check return value equals true ('1')
    assert return_bool.result.response == [1]

    return_bool = await Account2Signer.send_transaction(account2, stakingPool.contract_address, 'unstake_claim_rewards', [])
    # check return value equals true ('1')
    assert return_bool.result.response == [1]

    execution_info = await erc20Reward.balanceOf(account1.contract_address).call()
    account1_balance = execution_info.result.balance

    execution_info = await erc20Reward.balanceOf(account2.contract_address).call()
    account2_balance = execution_info.result.balance

    expected_account1_balance = div_rem_uint(
        mul_uint(reward_amount, stake_amount_account1), total_stake)[0]
    expected_account2_balance = div_rem_uint(
        mul_uint(reward_amount, stake_amount_account2), total_stake)[0]

    assert account1_balance == expected_account1_balance
    assert account2_balance == expected_account2_balance


@pytest.mark.asyncio
async def test_depositProportionalRewardsOverTime(after_initializer):
    starknet, erc20Stake, erc20Reward, stakingPool, owner, account1, account2 = after_initializer

    reward_amount1 = uint(100)
    reward_amount2 = uint(100)

    stake_amount_account1 = uint(1)
    stake_amount_account2 = uint(1)
    total_stake = add_uint(stake_amount_account1, stake_amount_account2)

    reward_amount = 100

    # stake
    return_bool = await Account1Signer.send_transaction(account1, stakingPool.contract_address, 'stake', [*stake_amount_account1])
    # check return value equals true ('1')
    assert return_bool.result.response == [1]

    return_bool = await OwnerSigner.send_transaction(owner, stakingPool.contract_address, 'deposit_reward', [*reward_amount1])
    # check return value equals true ('1')
    assert return_bool.result.response == [1]

    # stake
    return_bool = await Account2Signer.send_transaction(account2, stakingPool.contract_address, 'stake', [*stake_amount_account2])
    # check return value equals true ('1')
    assert return_bool.result.response == [1]

    return_bool = await OwnerSigner.send_transaction(owner, stakingPool.contract_address, 'deposit_reward', [*reward_amount2])
    # check return value equals true ('1')
    assert return_bool.result.response == [1]

    return_bool = await Account1Signer.send_transaction(account1, stakingPool.contract_address, 'unstake_claim_rewards', [])
    # check return value equals true ('1')
    assert return_bool.result.response == [1]

    return_bool = await Account2Signer.send_transaction(account2, stakingPool.contract_address, 'unstake_claim_rewards', [])
    # check return value equals true ('1')
    assert return_bool.result.response == [1]

    execution_info = await erc20Reward.balanceOf(account1.contract_address).call()
    account1_balance = execution_info.result.balance

    execution_info = await erc20Reward.balanceOf(account2.contract_address).call()
    account2_balance = execution_info.result.balance

    expected_account1_balance = add_uint(
        reward_amount1, div_rem_uint(reward_amount2, total_stake)[0])
    expected_account2_balance = div_rem_uint(reward_amount2, total_stake)[0]

    assert account1_balance == expected_account1_balance
    assert account2_balance == expected_account2_balance
