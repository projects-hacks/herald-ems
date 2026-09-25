import type { Contract } from "./contract";
import type { FactValue } from "./types";

/** Manual values use the same vocabulary as the server; blank never means zero or absent. */
export function manualValue(raw: string, meta: Contract["keys"][string]): FactValue {
  const text = raw.trim();
  if (!text) throw new Error("Enter a value. Blank does not mean absent.");
  if (meta.type === "bool") {
    if (text === "true") return true;
    if (text === "false") return false;
    throw new Error("Choose yes or no.");
  }
  if (meta.type === "int" || meta.type === "float") {
    const value = Number(text);
    if (!Number.isFinite(value) || (meta.type === "int" && !Number.isInteger(value))) throw new Error("Enter a valid " + (meta.type === "int" ? "whole number." : "number."));
    if (meta.range && (value < meta.range[0] || value > meta.range[1])) throw new Error(`Enter a value from ${meta.range[0]} to ${meta.range[1]} ${meta.unit ?? ""}.`);
    return value;
  }
  if (meta.type === "list") {
    if (text === "[]") return [];
    const items = text.split(",").map((item) => item.trim()).filter(Boolean);
    if (!items.length) throw new Error("Enter one or more items, or [] for explicitly none.");
    return items;
  }
  return text;
}
