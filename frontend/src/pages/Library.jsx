import StoryCollection from "../components/StoryCollection";
import { IconLibrary } from "../components/icons";

export default function Library() {
  return (
    <StoryCollection
      status="approved"
      index="03"
      title="Library"
      description="Approved stories, eligible for the publishing workflow. Nothing here is posted anywhere automatically."
      empty={{
        icon: IconLibrary,
        title: "The library is empty.",
        body: "Stories you approve on the review desk are shelved here, ready for publishing.",
      }}
    />
  );
}
