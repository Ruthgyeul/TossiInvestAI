// 모든 슬래시 명령어 모듈을 취합한다. index.ts가 여기서 등록·디스패치용 Map을 가져다 쓴다.
import { commands as backtestCommands } from "./backtest.js";
import { commands as buyCommands } from "./buy.js";
import { commands as cancelCommands } from "./cancel.js";
import { commands as dryrunCommands } from "./dryrun.js";
import { commands as fundCommands } from "./fund.js";
import { commands as healthCommands } from "./health.js";
import { commands as reportCommands } from "./report.js";
import { commands as resumeCommands } from "./resume.js";
import { commands as sellCommands } from "./sell.js";
import { commands as statusCommands } from "./status.js";
import { commands as stopCommands } from "./stop.js";
import type { BotCommand } from "./types.js";
import { commands as versionCommands } from "./version.js";
import { commands as watchlistCommands } from "./watchlist.js";

export const commands: BotCommand[] = [
  ...backtestCommands,
  ...buyCommands,
  ...cancelCommands,
  ...dryrunCommands,
  ...fundCommands,
  ...healthCommands,
  ...reportCommands,
  ...resumeCommands,
  ...sellCommands,
  ...statusCommands,
  ...stopCommands,
  ...versionCommands,
  ...watchlistCommands,
];

export const commandMap: Map<string, BotCommand> = new Map(commands.map((c) => [c.data.name, c]));
