# Copyright (c) 2018 HarryR. All Rights Reserved.
# SPDX-License-Identifier: GPL-3.0+

from random import randint
from binascii import hexlify

from ..utils import require
from ..ethrpc import EthJsonRpc

from ..lithium.common import proof_for_tx, proof_for_event, link_wait


PROVER_ADDR = '0xe982e462b094850f12af94d21d470e21be9d0e9c'
LINK_ADDR = '0xcfeb869f69431e42cdb54a4f4f105c19c080a601'

SWAP_CONTRACT = '0x254dffcd3277c0b1660f6d42efbb754edababc2b'
TOKEN_CONTRACT = '0xc89ce4735882c9f0f0fe26686c53074e09b0d550'

ACCOUNT_ALICE = '0x90f8bf6a479f320ead074411a4b0e7944ea8c9c1'
ACCOUNT_BOB = '0xffcf8fdee72ac11b5c542428b35eef5769c409f0'


def main():
    rpc_a = EthJsonRpc('127.0.0.1', 8545)
    link_a = rpc_a.proxy('../solidity/build/contracts/LithiumLink.json', LINK_ADDR)
    swap_a = rpc_a.proxy('../solidity/build/contracts/ExampleSwap.json', SWAP_CONTRACT, ACCOUNT_ALICE)
    token_a = rpc_a.proxy('../solidity/build/contracts/ExampleERC20Token.json', TOKEN_CONTRACT, ACCOUNT_ALICE)

    rpc_b = EthJsonRpc('127.0.0.1', 8546)
    link_b = rpc_b.proxy('../solidity/build/contracts/LithiumLink.json', LINK_ADDR)
    swap_b = rpc_b.proxy('../solidity/build/contracts/ExampleSwap.json', SWAP_CONTRACT, ACCOUNT_BOB)
    token_b = rpc_b.proxy('../solidity/build/contracts/ExampleERC20Token.json', TOKEN_CONTRACT, ACCOUNT_BOB)

    swap_guid = randint(1, 1 << 255)

    alice_value = randint(1024, 10240)
    bob_value = 0
    while bob_value != alice_value:
        bob_value = randint(1024, 10240)

    # Create Alice's tokens, approve swap contract to use them
    print("A: mint + approve")
    alice_balance_begin = token_a.balanceOf(ACCOUNT_ALICE)
    token_a.mint(ACCOUNT_ALICE, alice_value).wait(raise_on_error=True)
    alice_balance_aftermint = token_a.balanceOf(ACCOUNT_ALICE)
    require((alice_balance_aftermint - alice_balance_begin) == alice_value)

    # Approve swap contract to use Alice's tokens
    token_a.approve(SWAP_CONTRACT, alice_value).wait(raise_on_error=True)
    require(token_a.allowance(ACCOUNT_ALICE, SWAP_CONTRACT) == alice_value)

    # Create Bob's tokens, approve swap contract to use them
    print("B: mint + approve")
    bob_balance_begin = token_b.balanceOf(ACCOUNT_BOB)
    token_b.mint(ACCOUNT_BOB, bob_value).wait(raise_on_error=True)
    bob_balance_aftermint = token_b.balanceOf(ACCOUNT_BOB)
    require((bob_balance_aftermint - bob_balance_begin) == bob_value)

    # Approve swap contract to use Bob's tokens
    token_b.approve(SWAP_CONTRACT, bob_value).wait(raise_on_error=True)
    require(token_b.allowance(ACCOUNT_BOB, SWAP_CONTRACT) == bob_value)

    # Session struct
    RC_ALICE = (PROVER_ADDR, 1, SWAP_CONTRACT)
    RC_BOB = (PROVER_ADDR, 1, SWAP_CONTRACT)
    SESSION_SIDE_ALICE = ((RC_ALICE), TOKEN_CONTRACT, ACCOUNT_ALICE, alice_value)
    SESSION_SIDE_BOB = ((RC_BOB), TOKEN_CONTRACT, ACCOUNT_BOB, bob_value)
    SESSION = (1, SESSION_SIDE_ALICE, SESSION_SIDE_BOB)

    # On chain A, perform Propose as Alice
    alice_balance_before_propose = token_a.balanceOf(ACCOUNT_ALICE)
    swap_balance_before_propose = token_a.balanceOf(SWAP_CONTRACT)
    print("A: Propose")
    propose_tx = swap_a.TransitionAlicePropose(swap_guid, SESSION)
    propose_receipt = propose_tx.wait(raise_on_error=True)
    propose_proof = proof_for_tx(rpc_a, propose_tx)
    print(" - propose receipt", propose_receipt)
    print(" - propose proof", hexlify(propose_proof))

    # Verify Alice's balance has reduced
    require(token_a.balanceOf(ACCOUNT_ALICE) == (alice_balance_before_propose - alice_value))
    require(token_a.balanceOf(SWAP_CONTRACT) == (swap_balance_before_propose + alice_value))

    # On chain B, perform Accept as Bob
    link_wait(link_b, propose_proof)
    bob_balance_before_accept = token_b.balanceOf(ACCOUNT_BOB)
    swap_balance_before_accept = token_b.balanceOf(SWAP_CONTRACT)
    print("B: Accept")
    accept_tx = swap_b.TransitionBobAccept(swap_guid, SESSION, propose_proof)
    accept_receipt = accept_tx.wait(raise_on_error=True)
    accept_proof = proof_for_event(rpc_b, accept_tx, 0)
    print(" - accept receipt", accept_receipt)
    print(" - accept proof", hexlify(accept_proof))

    # Verify Bob's balance has reduced
    require(token_b.balanceOf(ACCOUNT_BOB) == (bob_balance_before_accept - bob_value))
    require(token_b.balanceOf(SWAP_CONTRACT) == (swap_balance_before_accept + bob_value))

    # On chain A, perform Withdraw as Bob
    print("A: Bob Withdraw")
    bob_balance_before_withdraw = token_a.balanceOf(ACCOUNT_BOB)
    swap_a_balance_before_withdraw = token_a.balanceOf(SWAP_CONTRACT)
    link_wait(link_a, accept_proof)
    bob_withdraw_tx = swap_a.TransitionBobWithdraw(swap_guid, accept_proof)
    bob_withdraw_receipt = bob_withdraw_tx.wait(raise_on_error=True)
    print(" - bob withdraw receipt", bob_withdraw_receipt)

    # Verify Bob now has Alice's tokens
    require(token_a.balanceOf(ACCOUNT_BOB) == (bob_balance_before_withdraw + alice_value))
    require(token_a.balanceOf(SWAP_CONTRACT) == (swap_a_balance_before_withdraw - alice_value))

    # On chain B, perform Withdraw as Alice
    print("B: Alice Withdraw")
    alice_balance_before_withdraw = token_b.balanceOf(ACCOUNT_ALICE)
    swap_b_balance_before_withdraw = token_b.balanceOf(SWAP_CONTRACT)
    alice_withdraw_tx = swap_b.TransitionAliceWithdraw(swap_guid)
    alice_withdraw_receipt = alice_withdraw_tx.wait(raise_on_error=True)
    print(" - alice withdraw receipt", alice_withdraw_receipt)

    # Verify Alice now has bob's tokens
    require(token_b.balanceOf(ACCOUNT_ALICE) == (alice_balance_before_withdraw + bob_value))
    require(token_b.balanceOf(SWAP_CONTRACT) == (swap_b_balance_before_withdraw - bob_value))


if __name__ == "__main__":
    main()
