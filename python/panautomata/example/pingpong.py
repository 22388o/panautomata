# Copyright (c) 2018 HarryR. All Rights Reserved.
# SPDX-License-Identifier: GPL-3.0+

from random import randint
from binascii import hexlify

from ..utils import u256be
from ..ethrpc import EthJsonRpc
from ..lithium.common import proof_for_tx, proof_for_event, link_wait


MOCK_PROVER = '0x5b1869d9a4c187f2eaa108f3062412ecf0526b24'

LINK_ADDRESS = '0xcfeb869f69431e42cdb54a4f4f105c19c080a601'
REAL_PROVER = '0xe982e462b094850f12af94d21d470e21be9d0e9c'

ACCOUNT_A = '0x90f8bf6a479f320ead074411a4b0e7944ea8c9c1'
CONTRACT_A = '0xd833215cbcc3f914bd1c9ece3ee7bf8b14f841bb'

# ACCOUNT_B = '0xffcf8fdee72ac11b5c542428b35eef5769c409f0'
CONTRACT_B = '0x9561c133dd8580860b6b7e504bc5aa500f0f06a7'


def main():
    guid = randint(1, 1 << 255)

    rpc_a = EthJsonRpc('127.0.0.1', 8545)
    link_a = rpc_a.proxy('../solidity/build/contracts/LithiumLink.json', LINK_ADDRESS)
    alice = rpc_a.proxy('../solidity/build/contracts/ExamplePingPongA.json', CONTRACT_A, ACCOUNT_A)

    rpc_b = EthJsonRpc('127.0.0.1', 8546)
    link_b = rpc_b.proxy('../solidity/build/contracts/LithiumLink.json', LINK_ADDRESS)
    bob = rpc_b.proxy('../solidity/build/contracts/ExamplePingPongB.json', CONTRACT_B, ACCOUNT_A)

    session_side_alice = (REAL_PROVER, 1, CONTRACT_A)
    session_side_bob = (REAL_PROVER, 1, CONTRACT_B)
    session = (session_side_alice, session_side_bob, 1)

    print("Guid", hexlify(u256be(guid)))

    print("Start")
    tx = alice.Start(guid, session)
    tx.wait()
    start_proof = proof_for_tx(rpc_a, tx)

    print("ReceiveStart")
    link_wait(link_b, start_proof)
    tx = bob.ReceiveStart(guid, session, start_proof)
    tx.wait()
    ping_proof = proof_for_event(rpc_b, tx, 0)

    for _ in range(0, 5):
        print("ReceivePing")
        link_wait(link_a, ping_proof)
        tx = alice.ReceivePing(guid, ping_proof)
        pong_proof = proof_for_event(rpc_a, tx, 0)
        tx.wait()

        print("ReceivePong")
        link_wait(link_b, pong_proof)
        tx = bob.ReceivePong(guid, pong_proof)
        ping_proof = proof_for_event(rpc_b, tx, 0)
        tx.wait()


if __name__ == "__main__":
    main()
