/* Project-authored research copy. Market text is translated separately by the configured LLM. */
(() => {
  const strategies = {
    '天气': {
      category:'Weather',priority:'First research track: possible weather-model advantage',
      signal:'Map the specified station’s observations, forecast distribution and historical errors to probabilities for each temperature interval. Compare them with executable asks after fees, and rule out low intervals that the observed maximum has already exceeded.',
      data:['Station, units, date and cutoff time in each market’s rules','Station observations, designated settlement source and fallback source','Ensemble forecasts and station-error calibration','Order book and feeSchedule','Interval boundaries and rounding'],
      failure:'A city temperature in a weather app cannot replace the specified airport station. Forecasts are not observations. Fallback sources, missing-data outcomes, revisions and Celsius/Fahrenheit boundaries can change settlement.',
      validation:'Use rolling holdout backtests for calibration, Brier score and expected return after costs for each interval, then observe live paper trades. No backtested probability model is currently available.'
    },
    '体育': {
      category:'Sports',priority:'First observation track: complete sets and pregame pricing; live-game signals come later',
      signal:'Scan net price gaps across mutually exclusive outcomes in the same game. Compare independent pregame probabilities with market asks, and research market-making conditions using liquidity, spreads and the event calendar.',
      data:['Event, team and schedule mapping','Moneyline, spread and total settlement rules','Full game, regulation time and overtime distinctions','Independent pregame odds without bookmaker margin, and lineup information','Order book depth, secondsDelay and fees','Reliable scores and recorded feed delays'],
      failure:'Draws, overtime, cancellations, postponements and mismatched lines can break a hedge. Score feeds may lag. Fees and execution of only one leg can consume a small pricing advantage.',
      validation:'Split paper backtests by the time pregame information became available. Do not treat faster score updates as a demonstrated advantage.'
    },
    '加密': {
      category:'Crypto',priority:'Second track: collect data and backtest short-duration markets first',
      signal:'Check complete-set net gaps within one condition and consistency across thresholds or intervals with the same expiry and settlement source. Research TWAP-aware probability and quote differences.',
      data:['Reference asset, starting price to beat and expiry','Chainlink TWAP required by the market','Second-by-second order books, trades and delays','External spot prices and volatility','Fees and on-chain balances'],
      failure:'An exchange spot price is not a Chainlink TWAP. Different maturities or thresholds do not form a direct hedge. Short-duration fees and execution competition can be substantial, and some reference feeds require credentials.',
      validation:'Pin market-rule versions and raw second-by-second data. Replay information in its original time order, simulate fills level by level and account for fees.'
    },
    '政治/宏观经济': {
      category:'Politics / macroeconomics',priority:'Second track: rule relationships and event calendars; directional automation comes later',
      signal:'Check inconsistencies after costs across candidate sets, monotonic thresholds or deadlines with matching settlement definitions. Research official release calendars, liquidity changes and independent probability models.',
      data:['Complete original rules and additional context','Related-market dependency graph and completeness','Specified Fed, BLS or election-agency sources and release times','Order book depth, fees, tied-up capital and resolution status'],
      failure:'Deadlines, initial versus revised statistics, and winning, inauguration or nomination definitions can differ. Incorrect exclusivity assumptions, resolution disputes and long capital lockups matter. Common-sense inference cannot replace explicit rules.',
      validation:'Have a person verify logical relationships and retain rule snapshots. Without a clear hedge and executable net profit, label the result a research candidate.'
    }
  };
  const repos = {
    'Polymarket/ts-sdk': {description:'@polymarket/client is the recommended starting point for new TypeScript projects, with unified REST, WebSocket and trading workflows.',limits:['Minor 0.x releases may break compatibility; pin the version.']},
    'Polymarket/py-sdk': {learn:['Retry-After parsing for seconds and HTTP dates, with typed errors','Separate pagination states for has_more and limit_reached'],decision:'Adapted ideas for rate-limit recovery, catalog snapshots and coverage states.',limits:['131 stars at review; retained as a current compatibility reference. Trading dependencies were not installed.']},
    'Polymarket/py-clob-client-v2': {description:'A narrowly scoped CLOB client, useful as a migration reference for existing V2 code.',limits:['Its README recommends py-sdk for new projects.','token_id and position_id use different protocol routing.']},
    'Polymarket/clob-client-v2': {description:'A CLOB data and order client, retained as a migration reference for existing code.',limits:['Its README recommends ts-sdk for new projects.']},
    '0106ss/polymarket-market-scanner': {learn:['Existing foundation for public data collection, depth calculations and simulation records'],decision:'Reused the MIT-licensed foundation, retaining its author attribution and license.',limits:['Upstream limitations have been addressed progressively in this project; see UPSTREAM.txt.']},
    'jlinnnn/polymarket-cli': {description:'Typer/httpx, Gamma search, price history and FastAPI serve provide ideas for JSON output and a local interface.',limits:['Two commits and zero stars at review provide limited maintenance evidence.','Heuristic momentum signals have no verified returns; this is not an L2 arbitrage engine.']},
    'warproxxx/poly-maker': {learn:['Order book spreads, near-price depth, imbalance and microprice','Separate data and strategy layers, with independently inspectable state and event cooldowns'],decision:'Adapted the metric design through an independent Decimal implementation.',limits:['This review used metrics and data structures only. Wallet, inventory and market-making execution were not included. Reward ranking has not been backtested locally.']},
    'matthewnyc2/arbitrage': {description:'Python, FastAPI, HTMX and SQLite; level-by-level depth, multiple-outcome combinations, delayed paper fills and risk gates.',limits:['Still depends on the old py-clob-client>=0.20; its live executor cannot be used directly.','“Production-grade” and “60 tests” are author claims that were not independently verified.','Legs are not atomic; completeness of outcome sets and augmented negRisk conditions must be checked.']},
    'Polymarket/real-time-data-client': {learn:['Separate connection state, subscriptions and message handling','Public reference-price sources may support future research'],decision:'Improved message deduplication and used connection lifecycle patterns as a reference.',limits:['RTDS is a different kind of data feed and cannot replace a CLOB order book. The reviewed implementation had reconnection and default-parameter edge cases.']},
    'Polymarket/polymarket-subgraph': {learn:['Archive condition/token identifiers, trades and historical metrics','Idempotent records and explicit metric units'],decision:'Retained as a future historical-research reference; no source code was copied in this review.',limits:['LGPL-3.0; indexing has latency and cumulative trade entities are not live L2 orders.']},
    'Polymarket/py-clob-client': {learn:['Batch order books, parameter caching and explicit invalidation','Separate public reads from authenticated trading interfaces'],decision:'Retained design ideas and implemented them independently against current API specifications.',limits:['Archived; old APIs and signing code are not runtime dependencies.']},
    'Polymarket/clob-client': {learn:['Typed order book and batch-query responses','Pagination progress and cache lifecycles'],decision:'Retained as a design reference; the old SDK was not integrated.',limits:['Archived; its old pagination termination marker does not apply to Gamma keyset pagination.']},
    'Polymarket/polymarket-cli': {learn:['Search, filter, detail and JSON-output workflows','Structured health status separated from presentation'],decision:'Adapted request, rate-limit and retry counters for the runtime monitor.',limits:['The README claims MIT, but no LICENSE file was found and the complete license was not verified. Used as a behavior reference only.']},
    'Jon-Becker/prediction-market-analysis': {learn:['Write historical data in Parquet chunks and resume indexing progress','Separate collection from reproducible analysis for future industry backtests'],decision:'Source reviewed as a reference for future history and backtest modules.',limits:['Its compressed dataset is about 36 GiB and was not downloaded or integrated. Historical trades are not currently executable order books.']},
    'pmxt-dev/pmxt': {learn:['Unified outcome order books with data queries separated from output','Quantity limits and cursor termination tests, from its Kalshi pagination code'],decision:'Source reviewed; applied independent token handling and explicit pagination boundaries.',limits:['The SDK includes trading capabilities and was not added as a dependency. This project continues to use Decimal for amounts.','Pagination tests informed boundary design; they are not Polymarket API specifications. Cross-platform quotes are not implemented.']}
  };
  window.ResearchCopy = {strategies,repos};
})();
