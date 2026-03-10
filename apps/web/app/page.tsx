import { ReviewWorkbench } from "@/components/ReviewWorkbench";
import { mockRunDetail } from "@/lib/mock-data";

export default function HomePage() {
  return <ReviewWorkbench initialRun={mockRunDetail} />;
}
