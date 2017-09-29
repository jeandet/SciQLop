#include "Data/DataSeries.h"
#include "Data/ScalarSeries.h"
#include "Data/VectorSeries.h"

#include <cmath>

#include <QObject>
#include <QtTest>

Q_DECLARE_METATYPE(std::shared_ptr<ScalarSeries>)
Q_DECLARE_METATYPE(std::shared_ptr<VectorSeries>)

namespace {

using DataContainer = std::vector<double>;

void validateRange(DataSeriesIterator first, DataSeriesIterator last, const DataContainer &xData,
                   const DataContainer &valuesData)
{
    QVERIFY(std::equal(first, last, xData.cbegin(), xData.cend(),
                       [](const auto &it, const auto &expectedX) { return it.x() == expectedX; }));
    QVERIFY(std::equal(
        first, last, valuesData.cbegin(), valuesData.cend(),
        [](const auto &it, const auto &expectedVal) { return it.value() == expectedVal; }));
}

void validateRange(DataSeriesIterator first, DataSeriesIterator last, const DataContainer &xData,
                   const std::vector<DataContainer> &valuesData)
{
    QVERIFY(std::equal(first, last, xData.cbegin(), xData.cend(),
                       [](const auto &it, const auto &expectedX) { return it.x() == expectedX; }));
    for (auto i = 0; i < valuesData.size(); ++i) {
        auto componentData = valuesData.at(i);

        QVERIFY(std::equal(
            first, last, componentData.cbegin(), componentData.cend(),
            [i](const auto &it, const auto &expectedVal) { return it.value(i) == expectedVal; }));
    }
}

} // namespace

class TestDataSeries : public QObject {
    Q_OBJECT
private:
    template <typename T>
    void testValuesBoundsStructure()
    {
        // ////////////// //
        // Test structure //
        // ////////////// //

        // Data series to get values bounds
        QTest::addColumn<std::shared_ptr<T> >("dataSeries");

        // x-axis range
        QTest::addColumn<double>("minXAxis");
        QTest::addColumn<double>("maxXAxis");

        // Expected results
        QTest::addColumn<bool>(
            "expectedOK"); // Test is expected to be ok (i.e. method doesn't return end iterators)
        QTest::addColumn<double>("expectedMinValue");
        QTest::addColumn<double>("expectedMaxValue");
    }

    template <typename T>
    void testValuesBounds()
    {
        QFETCH(std::shared_ptr<T>, dataSeries);
        QFETCH(double, minXAxis);
        QFETCH(double, maxXAxis);

        QFETCH(bool, expectedOK);
        QFETCH(double, expectedMinValue);
        QFETCH(double, expectedMaxValue);

        auto minMaxIts = dataSeries->valuesBounds(minXAxis, maxXAxis);
        auto end = dataSeries->cend();

        // Checks iterators with expected result
        QCOMPARE(expectedOK, minMaxIts.first != end && minMaxIts.second != end);

        if (expectedOK) {
            auto compare = [](const auto &v1, const auto &v2) {
                return (std::isnan(v1) && std::isnan(v2)) || v1 == v2;
            };

            QVERIFY(compare(expectedMinValue, minMaxIts.first->minValue()));
            QVERIFY(compare(expectedMaxValue, minMaxIts.second->maxValue()));
        }
    }

    template <typename T>
    void testPurgeStructure()
    {
        // ////////////// //
        // Test structure //
        // ////////////// //

        // Data series to purge
        QTest::addColumn<std::shared_ptr<T> >("dataSeries");
        QTest::addColumn<double>("min");
        QTest::addColumn<double>("max");

        // Expected values after purge
        QTest::addColumn<DataContainer>("expectedXAxisData");
        QTest::addColumn<std::vector<DataContainer> >("expectedValuesData");
    }

    template <typename T>
    void testPurge()
    {
        QFETCH(std::shared_ptr<T>, dataSeries);
        QFETCH(double, min);
        QFETCH(double, max);

        dataSeries->purge(min, max);

        // Validates results
        QFETCH(DataContainer, expectedXAxisData);
        QFETCH(std::vector<DataContainer>, expectedValuesData);

        validateRange(dataSeries->cbegin(), dataSeries->cend(), expectedXAxisData,
                      expectedValuesData);
    }

    template <typename SourceType, typename DestType>
    void testMergeDifferentTypesStructure()
    {
        // ////////////// //
        // Test structure //
        // ////////////// //

        // Data series to merge
        QTest::addColumn<std::shared_ptr<DestType> >("dest");
        QTest::addColumn<std::shared_ptr<SourceType> >("source");

        // Expected values in the dest data series after merge
        QTest::addColumn<DataContainer>("expectedXAxisData");
        QTest::addColumn<DataContainer>("expectedValuesData");
    }

    template <typename SourceType, typename DestType>
    void testMergeDifferentTypes()
    {
        // Merges series
        QFETCH(std::shared_ptr<SourceType>, source);
        QFETCH(std::shared_ptr<DestType>, dest);

        dest->merge(source.get());

        // Validates results : we check that the merge is valid and the data series is sorted on its
        // x-axis data
        QFETCH(DataContainer, expectedXAxisData);
        QFETCH(DataContainer, expectedValuesData);

        validateRange(dest->cbegin(), dest->cend(), expectedXAxisData, expectedValuesData);
    }

private slots:

    /// Input test data
    /// @sa testCtor()
    void testCtor_data();

    /// Tests construction of a data series
    void testCtor();

    /// Input test data
    /// @sa testMerge()
    void testMerge_data();

    /// Tests merge of two data series
    void testMerge();

    /// Input test data
    /// @sa testMergeVectorInScalar()
    void testMergeVectorInScalar_data();

    /// Tests merge of vector series in scalar series
    void testMergeVectorInScalar();

    /// Input test data
    /// @sa testPurgeScalar()
    void testPurgeScalar_data();

    /// Tests purge of a scalar series
    void testPurgeScalar();

    /// Input test data
    /// @sa testPurgeVector()
    void testPurgeVector_data();

    /// Tests purge of a vector series
    void testPurgeVector();

    /// Input test data
    /// @sa testMinXAxisData()
    void testMinXAxisData_data();

    /// Tests get min x-axis data of a data series
    void testMinXAxisData();

    /// Input test data
    /// @sa testMaxXAxisData()
    void testMaxXAxisData_data();

    /// Tests get max x-axis data of a data series
    void testMaxXAxisData();

    /// Input test data
    /// @sa testXAxisRange()
    void testXAxisRange_data();

    /// Tests get x-axis range of a data series
    void testXAxisRange();

    /// Input test data
    /// @sa testValuesBoundsScalar()
    void testValuesBoundsScalar_data();

    /// Tests get values bounds of a scalar series
    void testValuesBoundsScalar();

    /// Input test data
    /// @sa testValuesBoundsVector()
    void testValuesBoundsVector_data();

    /// Tests get values bounds of a vector series
    void testValuesBoundsVector();
};

void TestDataSeries::testCtor_data()
{
    // ////////////// //
    // Test structure //
    // ////////////// //

    // x-axis data
    QTest::addColumn<DataContainer>("xAxisData");
    // values data
    QTest::addColumn<DataContainer>("valuesData");

    // expected x-axis data
    QTest::addColumn<DataContainer>("expectedXAxisData");
    // expected values data
    QTest::addColumn<DataContainer>("expectedValuesData");

    // ////////// //
    // Test cases //
    // ////////// //

    QTest::newRow("invalidData (different sizes of vectors)")
        << DataContainer{1., 2., 3., 4., 5.} << DataContainer{100., 200., 300.} << DataContainer{}
        << DataContainer{};

    QTest::newRow("sortedData") << DataContainer{1., 2., 3., 4., 5.}
                                << DataContainer{100., 200., 300., 400., 500.}
                                << DataContainer{1., 2., 3., 4., 5.}
                                << DataContainer{100., 200., 300., 400., 500.};

    QTest::newRow("unsortedData") << DataContainer{5., 4., 3., 2., 1.}
                                  << DataContainer{100., 200., 300., 400., 500.}
                                  << DataContainer{1., 2., 3., 4., 5.}
                                  << DataContainer{500., 400., 300., 200., 100.};

    QTest::newRow("unsortedData2")
        << DataContainer{1., 4., 3., 5., 2.} << DataContainer{100., 200., 300., 400., 500.}
        << DataContainer{1., 2., 3., 4., 5.} << DataContainer{100., 500., 300., 200., 400.};
}

void TestDataSeries::testCtor()
{
    // Creates series
    QFETCH(DataContainer, xAxisData);
    QFETCH(DataContainer, valuesData);

    auto series = std::make_shared<ScalarSeries>(std::move(xAxisData), std::move(valuesData),
                                                 Unit{}, Unit{});

    // Validates results : we check that the data series is sorted on its x-axis data
    QFETCH(DataContainer, expectedXAxisData);
    QFETCH(DataContainer, expectedValuesData);

    validateRange(series->cbegin(), series->cend(), expectedXAxisData, expectedValuesData);
}

namespace {

std::shared_ptr<ScalarSeries> createScalarSeries(DataContainer xAxisData, DataContainer valuesData)
{
    return std::make_shared<ScalarSeries>(std::move(xAxisData), std::move(valuesData), Unit{},
                                          Unit{});
}

std::shared_ptr<VectorSeries> createVectorSeries(DataContainer xAxisData, DataContainer xValuesData,
                                                 DataContainer yValuesData,
                                                 DataContainer zValuesData)
{
    return std::make_shared<VectorSeries>(std::move(xAxisData), std::move(xValuesData),
                                          std::move(yValuesData), std::move(zValuesData), Unit{},
                                          Unit{});
}

} // namespace

void TestDataSeries::testMerge_data()
{
    // ////////////// //
    // Test structure //
    // ////////////// //

    // Data series to merge
    QTest::addColumn<std::shared_ptr<ScalarSeries> >("dataSeries");
    QTest::addColumn<std::shared_ptr<ScalarSeries> >("dataSeries2");

    // Expected values in the first data series after merge
    QTest::addColumn<DataContainer>("expectedXAxisData");
    QTest::addColumn<DataContainer>("expectedValuesData");

    // ////////// //
    // Test cases //
    // ////////// //

    QTest::newRow("sortedMerge")
        << createScalarSeries({1., 2., 3., 4., 5.}, {100., 200., 300., 400., 500.})
        << createScalarSeries({6., 7., 8., 9., 10.}, {600., 700., 800., 900., 1000.})
        << DataContainer{1., 2., 3., 4., 5., 6., 7., 8., 9., 10.}
        << DataContainer{100., 200., 300., 400., 500., 600., 700., 800., 900., 1000.};

    QTest::newRow("unsortedMerge")
        << createScalarSeries({6., 7., 8., 9., 10.}, {600., 700., 800., 900., 1000.})
        << createScalarSeries({1., 2., 3., 4., 5.}, {100., 200., 300., 400., 500.})
        << DataContainer{1., 2., 3., 4., 5., 6., 7., 8., 9., 10.}
        << DataContainer{100., 200., 300., 400., 500., 600., 700., 800., 900., 1000.};

    QTest::newRow("unsortedMerge2 (merge not made because source is in the bounds of dest)")
        << createScalarSeries({1., 2., 8., 9., 10}, {100., 200., 800., 900., 1000.})
        << createScalarSeries({3., 4., 5., 6., 7.}, {300., 400., 500., 600., 700.})
        << DataContainer{1., 2., 8., 9., 10.} << DataContainer{100., 200., 800., 900., 1000.};

    QTest::newRow("unsortedMerge3")
        << createScalarSeries({3., 4., 5., 7., 8}, {300., 400., 500., 700., 800.})
        << createScalarSeries({1., 2., 3., 7., 10.}, {100., 200., 333., 777., 1000.})
        << DataContainer{1., 2., 3., 4., 5., 7., 8., 10.}
        << DataContainer{100., 200., 300., 400., 500., 700., 800., 1000.};

    QTest::newRow("emptySource") << createScalarSeries({3., 4., 5., 7., 8},
                                                       {300., 400., 500., 700., 800.})
                                 << createScalarSeries({}, {}) << DataContainer{3., 4., 5., 7., 8.}
                                 << DataContainer{300., 400., 500., 700., 800.};
}

void TestDataSeries::testMerge()
{
    // Merges series
    QFETCH(std::shared_ptr<ScalarSeries>, dataSeries);
    QFETCH(std::shared_ptr<ScalarSeries>, dataSeries2);

    dataSeries->merge(dataSeries2.get());

    // Validates results : we check that the merge is valid and the data series is sorted on its
    // x-axis data
    QFETCH(DataContainer, expectedXAxisData);
    QFETCH(DataContainer, expectedValuesData);

    validateRange(dataSeries->cbegin(), dataSeries->cend(), expectedXAxisData, expectedValuesData);
}

void TestDataSeries::testMergeVectorInScalar_data()
{
    testMergeDifferentTypesStructure<VectorSeries, ScalarSeries>();

    // ////////// //
    // Test cases //
    // ////////// //

    QTest::newRow("purgeVectorInScalar")
        << createScalarSeries({1., 2., 3., 4., 5.}, {100., 200., 300., 400., 500.})
        << createVectorSeries({6., 7., 8., 9., 10.}, {600., 700., 800., 900., 1000.},
                              {610., 710., 810., 910., 1010.}, {620., 720., 820., 920., 1020.})
        << DataContainer{1., 2., 3., 4., 5.} << DataContainer{100., 200., 300., 400., 500.};
}

void TestDataSeries::testMergeVectorInScalar()
{
    testMergeDifferentTypes<VectorSeries, ScalarSeries>();
}

void TestDataSeries::testPurgeScalar_data()
{
    testPurgeStructure<ScalarSeries>();

    // ////////// //
    // Test cases //
    // ////////// //

    QTest::newRow("purgeScalar") << createScalarSeries({1., 2., 3., 4., 5.},
                                                       {100., 200., 300., 400., 500.})
                                 << 2. << 4. << DataContainer{2., 3., 4.}
                                 << std::vector<DataContainer>{{200., 300., 400.}};
    QTest::newRow("purgeScalar1 (min/max swap)")
        << createScalarSeries({1., 2., 3., 4., 5.}, {100., 200., 300., 400., 500.}) << 4. << 2.
        << DataContainer{2., 3., 4.} << std::vector<DataContainer>{{200., 300., 400.}};
    QTest::newRow("purgeScalar2") << createScalarSeries({1., 2., 3., 4., 5.},
                                                        {100., 200., 300., 400., 500.})
                                  << 0. << 2.5 << DataContainer{1., 2.}
                                  << std::vector<DataContainer>{{100., 200.}};
    QTest::newRow("purgeScalar3") << createScalarSeries({1., 2., 3., 4., 5.},
                                                        {100., 200., 300., 400., 500.})
                                  << 3.5 << 7. << DataContainer{4., 5.}
                                  << std::vector<DataContainer>{{400., 500.}};
    QTest::newRow("purgeScalar4") << createScalarSeries({1., 2., 3., 4., 5.},
                                                        {100., 200., 300., 400., 500.})
                                  << 0. << 7. << DataContainer{1., 2., 3., 4., 5.}
                                  << std::vector<DataContainer>{{100., 200., 300., 400., 500.}};
    QTest::newRow("purgeScalar5") << createScalarSeries({1., 2., 3., 4., 5.},
                                                        {100., 200., 300., 400., 500.})
                                  << 5.5 << 7. << DataContainer{} << std::vector<DataContainer>{{}};
}

void TestDataSeries::testPurgeScalar()
{
    testPurge<ScalarSeries>();
}

void TestDataSeries::testPurgeVector_data()
{
    testPurgeStructure<VectorSeries>();

    // ////////// //
    // Test cases //
    // ////////// //

    QTest::newRow("purgeVector") << createVectorSeries({1., 2., 3., 4., 5.}, {6., 7., 8., 9., 10.},
                                                       {11., 12., 13., 14., 15.},
                                                       {16., 17., 18., 19., 20.})
                                 << 2. << 4. << DataContainer{2., 3., 4.}
                                 << std::vector<DataContainer>{
                                        {7., 8., 9.}, {12., 13., 14.}, {17., 18., 19.}};
}

void TestDataSeries::testPurgeVector()
{
    testPurge<VectorSeries>();
}

void TestDataSeries::testMinXAxisData_data()
{
    // ////////////// //
    // Test structure //
    // ////////////// //

    // Data series to get min data
    QTest::addColumn<std::shared_ptr<ScalarSeries> >("dataSeries");

    // Min data
    QTest::addColumn<double>("min");

    // Expected results
    QTest::addColumn<bool>(
        "expectedOK"); // if true, expects to have a result (i.e. the iterator != end iterator)
    QTest::addColumn<double>(
        "expectedMin"); // Expected value when method doesn't return end iterator

    // ////////// //
    // Test cases //
    // ////////// //

    QTest::newRow("minData1") << createScalarSeries({1., 2., 3., 4., 5.},
                                                    {100., 200., 300., 400., 500.})
                              << 0. << true << 1.;
    QTest::newRow("minData2") << createScalarSeries({1., 2., 3., 4., 5.},
                                                    {100., 200., 300., 400., 500.})
                              << 1. << true << 1.;
    QTest::newRow("minData3") << createScalarSeries({1., 2., 3., 4., 5.},
                                                    {100., 200., 300., 400., 500.})
                              << 1.1 << true << 2.;
    QTest::newRow("minData4") << createScalarSeries({1., 2., 3., 4., 5.},
                                                    {100., 200., 300., 400., 500.})
                              << 5. << true << 5.;
    QTest::newRow("minData5") << createScalarSeries({1., 2., 3., 4., 5.},
                                                    {100., 200., 300., 400., 500.})
                              << 5.1 << false << std::numeric_limits<double>::quiet_NaN();
    QTest::newRow("minData6") << createScalarSeries({}, {}) << 1.1 << false
                              << std::numeric_limits<double>::quiet_NaN();
}

void TestDataSeries::testMinXAxisData()
{
    QFETCH(std::shared_ptr<ScalarSeries>, dataSeries);
    QFETCH(double, min);

    QFETCH(bool, expectedOK);
    QFETCH(double, expectedMin);

    auto it = dataSeries->minXAxisData(min);

    QCOMPARE(expectedOK, it != dataSeries->cend());

    // If the method doesn't return a end iterator, checks with expected value
    if (expectedOK) {
        QCOMPARE(expectedMin, it->x());
    }
}

void TestDataSeries::testMaxXAxisData_data()
{
    // ////////////// //
    // Test structure //
    // ////////////// //

    // Data series to get max data
    QTest::addColumn<std::shared_ptr<ScalarSeries> >("dataSeries");

    // Max data
    QTest::addColumn<double>("max");

    // Expected results
    QTest::addColumn<bool>(
        "expectedOK"); // if true, expects to have a result (i.e. the iterator != end iterator)
    QTest::addColumn<double>(
        "expectedMax"); // Expected value when method doesn't return end iterator

    // ////////// //
    // Test cases //
    // ////////// //

    QTest::newRow("maxData1") << createScalarSeries({1., 2., 3., 4., 5.},
                                                    {100., 200., 300., 400., 500.})
                              << 6. << true << 5.;
    QTest::newRow("maxData2") << createScalarSeries({1., 2., 3., 4., 5.},
                                                    {100., 200., 300., 400., 500.})
                              << 5. << true << 5.;
    QTest::newRow("maxData3") << createScalarSeries({1., 2., 3., 4., 5.},
                                                    {100., 200., 300., 400., 500.})
                              << 4.9 << true << 4.;
    QTest::newRow("maxData4") << createScalarSeries({1., 2., 3., 4., 5.},
                                                    {100., 200., 300., 400., 500.})
                              << 1.1 << true << 1.;
    QTest::newRow("maxData5") << createScalarSeries({1., 2., 3., 4., 5.},
                                                    {100., 200., 300., 400., 500.})
                              << 1. << true << 1.;
    QTest::newRow("maxData6") << createScalarSeries({}, {}) << 1.1 << false
                              << std::numeric_limits<double>::quiet_NaN();
}

void TestDataSeries::testMaxXAxisData()
{
    QFETCH(std::shared_ptr<ScalarSeries>, dataSeries);
    QFETCH(double, max);

    QFETCH(bool, expectedOK);
    QFETCH(double, expectedMax);

    auto it = dataSeries->maxXAxisData(max);

    QCOMPARE(expectedOK, it != dataSeries->cend());

    // If the method doesn't return a end iterator, checks with expected value
    if (expectedOK) {
        QCOMPARE(expectedMax, it->x());
    }
}

void TestDataSeries::testXAxisRange_data()
{
    // ////////////// //
    // Test structure //
    // ////////////// //

    // Data series to get x-axis range
    QTest::addColumn<std::shared_ptr<ScalarSeries> >("dataSeries");

    // Min/max values
    QTest::addColumn<double>("min");
    QTest::addColumn<double>("max");

    // Expected values
    QTest::addColumn<DataContainer>("expectedXAxisData");
    QTest::addColumn<DataContainer>("expectedValuesData");

    // ////////// //
    // Test cases //
    // ////////// //

    QTest::newRow("xAxisRange") << createScalarSeries({1., 2., 3., 4., 5.},
                                                      {100., 200., 300., 400., 500.})
                                << -1. << 3.2 << DataContainer{1., 2., 3.}
                                << DataContainer{100., 200., 300.};
    QTest::newRow("xAxisRange1 (min/max swap)")
        << createScalarSeries({1., 2., 3., 4., 5.}, {100., 200., 300., 400., 500.}) << 3.2 << -1.
        << DataContainer{1., 2., 3.} << DataContainer{100., 200., 300.};
    QTest::newRow("xAxisRange2") << createScalarSeries({1., 2., 3., 4., 5.},
                                                       {100., 200., 300., 400., 500.})
                                 << 1. << 4. << DataContainer{1., 2., 3., 4.}
                                 << DataContainer{100., 200., 300., 400.};
    QTest::newRow("xAxisRange3") << createScalarSeries({1., 2., 3., 4., 5.},
                                                       {100., 200., 300., 400., 500.})
                                 << 1. << 3.9 << DataContainer{1., 2., 3.}
                                 << DataContainer{100., 200., 300.};
    QTest::newRow("xAxisRange4") << createScalarSeries({1., 2., 3., 4., 5.},
                                                       {100., 200., 300., 400., 500.})
                                 << 0. << 0.9 << DataContainer{} << DataContainer{};
    QTest::newRow("xAxisRange5") << createScalarSeries({1., 2., 3., 4., 5.},
                                                       {100., 200., 300., 400., 500.})
                                 << 0. << 1. << DataContainer{1.} << DataContainer{100.};
    QTest::newRow("xAxisRange6") << createScalarSeries({1., 2., 3., 4., 5.},
                                                       {100., 200., 300., 400., 500.})
                                 << 2.1 << 6. << DataContainer{3., 4., 5.}
                                 << DataContainer{300., 400., 500.};
    QTest::newRow("xAxisRange7") << createScalarSeries({1., 2., 3., 4., 5.},
                                                       {100., 200., 300., 400., 500.})
                                 << 6. << 9. << DataContainer{} << DataContainer{};
    QTest::newRow("xAxisRange8") << createScalarSeries({1., 2., 3., 4., 5.},
                                                       {100., 200., 300., 400., 500.})
                                 << 5. << 9. << DataContainer{5.} << DataContainer{500.};
}

void TestDataSeries::testXAxisRange()
{
    QFETCH(std::shared_ptr<ScalarSeries>, dataSeries);
    QFETCH(double, min);
    QFETCH(double, max);

    QFETCH(DataContainer, expectedXAxisData);
    QFETCH(DataContainer, expectedValuesData);

    auto bounds = dataSeries->xAxisRange(min, max);
    validateRange(bounds.first, bounds.second, expectedXAxisData, expectedValuesData);
}

void TestDataSeries::testValuesBoundsScalar_data()
{
    testValuesBoundsStructure<ScalarSeries>();

    // ////////// //
    // Test cases //
    // ////////// //
    auto nan = std::numeric_limits<double>::quiet_NaN();

    QTest::newRow("scalarBounds1")
        << createScalarSeries({1., 2., 3., 4., 5.}, {100., 200., 300., 400., 500.}) << 0. << 6.
        << true << 100. << 500.;
    QTest::newRow("scalarBounds2")
        << createScalarSeries({1., 2., 3., 4., 5.}, {100., 200., 300., 400., 500.}) << 2. << 4.
        << true << 200. << 400.;
    QTest::newRow("scalarBounds3")
        << createScalarSeries({1., 2., 3., 4., 5.}, {100., 200., 300., 400., 500.}) << 0. << 0.5
        << false << nan << nan;
    QTest::newRow("scalarBounds4")
        << createScalarSeries({1., 2., 3., 4., 5.}, {100., 200., 300., 400., 500.}) << 5.1 << 6.
        << false << nan << nan;
    QTest::newRow("scalarBounds5")
        << createScalarSeries({1.}, {100.}) << 0. << 2. << true << 100. << 100.;
    QTest::newRow("scalarBounds6") << createScalarSeries({}, {}) << 0. << 2. << false << nan << nan;

    // Tests with NaN values: NaN values are not included in min/max search
    QTest::newRow("scalarBounds7")
        << createScalarSeries({1., 2., 3., 4., 5.}, {nan, 200., 300., 400., nan}) << 0. << 6.
        << true << 200. << 400.;
    QTest::newRow("scalarBounds8")
        << createScalarSeries({1., 2., 3., 4., 5.}, {nan, nan, nan, nan, nan}) << 0. << 6. << true
        << std::numeric_limits<double>::quiet_NaN() << std::numeric_limits<double>::quiet_NaN();
}

void TestDataSeries::testValuesBoundsScalar()
{
    testValuesBounds<ScalarSeries>();
}

void TestDataSeries::testValuesBoundsVector_data()
{
    testValuesBoundsStructure<VectorSeries>();

    // ////////// //
    // Test cases //
    // ////////// //
    auto nan = std::numeric_limits<double>::quiet_NaN();

    QTest::newRow("vectorBounds1")
        << createVectorSeries({1., 2., 3., 4., 5.}, {10., 15., 20., 13., 12.},
                              {35., 24., 10., 9., 0.3}, {13., 14., 12., 9., 24.})
        << 0. << 6. << true << 0.3 << 35.; // min/max in same component
    QTest::newRow("vectorBounds2")
        << createVectorSeries({1., 2., 3., 4., 5.}, {2.3, 15., 20., 13., 12.},
                              {35., 24., 10., 9., 4.}, {13., 14., 12., 9., 24.})
        << 0. << 6. << true << 2.3 << 35.; // min/max in same entry
    QTest::newRow("vectorBounds3")
        << createVectorSeries({1., 2., 3., 4., 5.}, {2.3, 15., 20., 13., 12.},
                              {35., 24., 10., 9., 4.}, {13., 14., 12., 9., 24.})
        << 2. << 3. << true << 10. << 24.;

    // Tests with NaN values: NaN values are not included in min/max search
    QTest::newRow("vectorBounds4")
        << createVectorSeries({1., 2.}, {nan, nan}, {nan, nan}, {nan, nan}) << 0. << 6. << true
        << nan << nan;
}

void TestDataSeries::testValuesBoundsVector()
{
    testValuesBounds<VectorSeries>();
}

QTEST_MAIN(TestDataSeries)
#include "TestDataSeries.moc"
