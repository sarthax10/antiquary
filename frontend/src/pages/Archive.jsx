import StoryCollection from "../components/StoryCollection";
import { IconArchive } from "../components/icons";

export default function Archive() {
  return (
    <StoryCollection
      status="rejected"
      index="04"
      title="Archive"
      description="Rejected stories. Kept, not deleted — anything here can go back to the review desk for another look."
      empty={{
        icon: IconArchive,
        title: "Nothing has been rejected.",
        body: "Stories you reject land here, and can always be sent back for another look.",
      }}
    />
  );
}
