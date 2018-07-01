# Copyright (c) 2016-2018 Clearmatics Technologies Ltd
# Copyright (c) 2018 HarryR. All Rights Reserved.
# SPDX-License-Identifier: LGPL-3.0+

"""
Lithium: Event Relayer between two Ethereum chains

Connects to two RPC endpoints, retrieves transactions and logs from one chain,
packs them, constructs merkle roots and submits them to the IonLink contract of
the other chain.

This tool was designed to facilitate the information swap between two EVM chains
and only works in one direction. To allow two-way communication, two Lithium
instances must be initialised.
"""

import time
import threading

# TODO: import logging, use logging

from ..utils import require
from ..merkle import merkle_tree

from .common import pack_txn, pack_log, process_block


class Lithium(object):
    """
    Process logs and transactions from the `rpc_from` chain, condensing them into merkle roots
    then relays them to the LithiumLink contract on the `rpc_to` chain.
    """
    def __init__(self, rpc_from, rpc_to, to_account, link_addr, batch_size):
        assert isinstance(batch_size, int)
        self._run_event = threading.Event()
        self._rpc_from = rpc_from
        self._batch_size = batch_size
        # XXX: extract ABI from package resources
        self.contract = rpc_to.proxy("../solidity/build/contracts/LithiumLink.json", link_addr, to_account)

    @property
    def running(self):
        return self._run_event.is_set()

    def process_block_group(self, block_group):
        """
        Process a group of blocks, returning the packed events and transactions
        """
        print("Processing block group")
        items = []
        group_tx_count = 0
        group_log_count = 0
        for block_height in block_group:
            block_items, tx_count, log_count = process_block(self._rpc_from, block_height)
            items.append((block_height, block_items))
            group_tx_count += tx_count
            group_log_count += log_count

        return items, group_tx_count, group_log_count

    def get_block_group(self):
        """
        Retrieve a list of block numbers which need to be synched to the `to` contract
        from the `from` network, in the order that they need to be synched.
        """
        synched_block = self.contract.LatestBlock()
        current_block = self._rpc_from.eth_blockNumber()
        print("Current block:", current_block)
        print("Synched needed:", synched_block)

        # On-chain `to` contract is synched up to the latest `from` block
        if synched_block == current_block:
            return None

        # TODO: simplify expression, reduce to single range() expression
        out_blocks = []
        for block_no in range(synched_block + 1, current_block + 1):
            out_blocks.append(block_no)
            if len(out_blocks) == self._batch_size:
                break

        return out_blocks

    def iter_blocks(self, interval=1):
        """
        Iterate through the on-chain block numbers in batches of N starting from `start`
        in the order that they need to be submitted to the on-chain Link contract.
        """
        while self.running:
            try:
                blocks = self.get_block_group()
                if blocks:
                    yield blocks
                time.sleep(interval)
            except KeyboardInterrupt:
                break

    def submit(self, batch):
        """Submit batch of merkle roots to LithiumLink"""
        print("Submitting batch of", len(batch), "blocks")
        for block_height, block_root in batch:
            print(" -", block_height, block_root)
        transaction = self.contract.Update(batch[0][0] - 1, [_[1] for _ in batch])
        receipt = transaction.wait()
        if int(receipt['status'], 16) == 0:
            raise RuntimeError("Error when submitting blocks! Receipt: " + str(receipt))

        # XXX: what happens when gas limit gets hit? (e.g. too many block submitted at once)
        # TODO: if successful, verify the latest root matches the one we submitted

    def run(self):
        """ Launches the etheventrelay on a thread"""
        require(False is self._run_event.is_set(), "Already running")
        self._run_event.set()

        print("Starting block iterator")

        batch = []
        for block_group in self.iter_blocks():
            items, group_tx_count, group_log_count = self.process_block_group(block_group)
            print("blocks %d-%d (%d tx, %d events)" % (min(block_group), max(block_group), group_tx_count, group_log_count))

            for block_height, block_items in items:
                _, root = merkle_tree(block_items)
                batch.append((block_height, root))

            if batch:
                self.submit(batch)
                batch = []

        # Submit any remaining items
        if batch:
            self.submit(batch)

    def stop(self):
        """Turn off the 'running' event, causing any loop to exit"""
        self._run_event.clear()
