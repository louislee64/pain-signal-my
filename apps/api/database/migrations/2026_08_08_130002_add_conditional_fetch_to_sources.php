<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * §38: "Do not download unchanged official datasets unnecessarily. Store:
     * last_modified, etag, dataset_version, last_successful_sync where
     * available."
     *
     * This lands in Milestone 7 because Milestone 7 is what makes ingestion
     * automatic. Fetching 945 rows by hand occasionally is harmless; fetching
     * them every night when the upstream file has not changed is what §38 is
     * telling us not to do — it wastes someone else's bandwidth, and data.gov.my
     * is a public service being used under its terms of use (§11).
     *
     * `last_successful_sync` is distinct from the existing `last_synced_at`, and
     * the difference matters: `last_synced_at` records that we talked to the
     * source, which includes a 304 Not Modified and a failure. This records that
     * we successfully got data. Conflating them would make a source that has
     * been erroring for a week look freshly synced.
     */
    public function up(): void
    {
        Schema::table('sources', function (Blueprint $table) {
            $table->string('etag')->nullable()->after('last_dataset_updated_at');
            $table->string('last_modified')->nullable()->after('etag');
            $table->string('dataset_version')->nullable()->after('last_modified');
            $table->timestamp('last_successful_sync')->nullable()->after('dataset_version');
        });
    }

    public function down(): void
    {
        Schema::table('sources', function (Blueprint $table) {
            $table->dropColumn(['etag', 'last_modified', 'dataset_version', 'last_successful_sync']);
        });
    }
};
