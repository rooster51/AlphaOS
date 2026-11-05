import { Header } from "@/components/shell/Header";
import { OptionsChain } from "./OptionsChain";

export default function OptionsPage() {
  return <>
    <Header title="Options Chain" subtitle="Public market data · SPY and QQQ" />
    <OptionsChain />
  </>;
}
