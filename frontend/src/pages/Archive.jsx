import DecidedList from "../components/DecidedList";

export default function Archive() {
  return (
    <DecidedList
      status="rejected"
      emptyTitle="Nothing rejected yet."
      emptySub="Rejected stories will collect here."
    />
  );
}
