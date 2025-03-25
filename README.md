# Overview of Modules

### `scraper.py`
- **TokenScraper**  
  - Fetches token metadata (creator, mint time, etc.) via Solscan API.  
  - Falls back to a local `step_0.json` file if API calls fail.  

- **MinterTransferScraper**  
  - Performs a breadth-first search (BFS) from the token’s **minter** address.  
  - At each “step,” retrieves outgoing transfers, forms child nodes, and saves progress to JSON (e.g., `step_1.json`).  
  - Supports a configurable maximum depth (`max_steps`) and brief delay between API calls.  

### `utils.py`
- **serialize_graph / deserialize_graph**  
  - Converts a tree of `AccountNode` objects into JSON-friendly structures (and back again).  
- **save_graph_state_to_json**  
  - Saves the BFS “root” and current “frontier” (list of addresses) in a single JSON file for incremental scraping or later reloading.

---

# Key Conclusions

1. **Meme Tokens = Star-Like Flows**  
   - Large address sets and negative out→in degree correlations indicate a few “whales” distributing tokens widely.  
   - One-directional edges dominate, leading to many small strongly connected components.  

2. **Fundamental Tokens = Smaller BFS Footprints**  
   - Minimal direct user-to-user transactions uncovered via BFS.  
   - Usage likely happens off-chain, via custodial services, or through specialized smart contracts.  

3. **Network Metrics Reveal Hype vs. Utility**  
   - Low clustering and broadcast-style flows are typical of hype-driven assets.  
   - Steady, functional tokens might show sparse on-chain distribution if most operations occur elsewhere.

Overall, systematic graph-building from the minter address highlights how **token type** (meme vs. fundamental) can profoundly shape on-chain footprints, even on a high-throughput blockchain like Solana.
