import { Header } from "@/components/shell/Header";
import { OptionsChain } from "./OptionsChain";

export default async function OptionsPage({
  searchParams,
}: {
  searchParams: Promise<{ symbol?: string }>;
}) {
  const params = await searchParams;
  const initialSymbol = params.symbol?.toUpperCase() === "QQQ" ? "QQQ" : "SPY";
  return <>
    <Header title="Options Chain" subtitle="Public market data · SPY and QQQ" />
    <OptionsChain initialSymbol={initialSymbol} />
  </>;
}
