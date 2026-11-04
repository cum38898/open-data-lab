import { daysLeft, statusOf, STATUS_LABEL, type StatusInput } from "./status";

export const SOON_DAYS = 14;

/** 状態チップの表示（クラスと文言）。ビルド時とブラウザの両方で同じものを使う */
export function chipFor(r: StatusInput, now: number = Date.now()): { cls: string; text: string; status: string } {
  const status = statusOf(r, now);
  if (status === "open") {
    const left = daysLeft(r.end, now);
    const est = r.end_estimated ? "（推定）" : "";
    if (left !== null && left <= SOON_DAYS) {
      return {
        cls: "status-soon",
        text: left === 0 ? `本日締切${est}` : `締切まであと${left}日${est}`,
        status,
      };
    }
    return { cls: "status-open", text: `${STATUS_LABEL.open}${est}`, status };
  }
  return { cls: `status-${status}`, text: STATUS_LABEL[status], status };
}
