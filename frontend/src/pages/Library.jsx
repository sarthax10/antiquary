import DecidedList from "../components/DecidedList";

export default function Library() {
  return (
    <DecidedList
      status="approved"
      emptyTitle="Nothing approved yet."
      emptySub="Approved stories will collect here, ready for the publish workflow."
      showPublish
    />
  );
}
